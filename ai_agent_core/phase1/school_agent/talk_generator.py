"""智能合规咨询话术生成（选校 Agent 步骤 5）。

两条硬约束：
1. 话术模板来自内控 RAG 库（机构自己审核过的合规版本），不由模型自由发挥
2. 生成结果必须再过一遍安全护栏；一旦命中红线，直接回退到标准模板
"""
from __future__ import annotations

from ...prompt.school_prompt import COMPLIANT_TALK_PROMPT
from ...schema.student_schema import StudentBasicInfo

INTENT_RULES = {
    # 顺序即优先级：先判"是否在问保录"，再判其他诉求，否则"保录前 50"会被名校执念截胡
    "保录询问": ["保录", "保过", "内推", "渠道", "稳录", "百分百", "保底进"],
    "低价诉求": ["便宜", "低价", "预算", "太贵", "打折", "优惠", "降价", "性价比"],
    "焦虑催结果": ["多久", "什么时候", "急", "来得及", "赶得上", "还没出", "会不会耽误"],
    "名校执念": ["qs", "排名", "前50", "top50", "g5", "名校", "藤校", "ucl", "lse", "ic ", "曼大", "港三"],
    "低分冲高": ["gpa低", "均分低", "分数不高", "低分", "冲一下", "能申上吗", "有希望吗"],
}

# 合规标准话术（机构内控库的离线兜底版本）
COMPLIANT_TEMPLATES = {
    "名校执念": (
        "理解您希望冲高排名的想法。需要说明的是，QS 排名靠前的项目通常对 GPA 和语言有硬门槛，"
        "能否录取由学校独立评审决定，我们无法承诺结果。我的建议是按冲刺/匹配/保底三档布局，"
        "既保留冲高机会，也确保有稳录的offer托底。"
    ),
    "低分冲高": (
        "以目前的分数，直接冲高排名项目风险较大。可行的路径是：优先看对均分要求相对灵活的项目，"
        "同时用实习/科研和文书把亮点做出来，另外加申 2 所匹配校确保有结果。"
        "录取结果最终由学校决定，我们不能做任何结果承诺。"
    ),
    "低价诉求": (
        "费用这边我们可以按您的预算调整方案：选学制更短、生活成本更低的地区，"
        "或者减少申请院校数量。但服务内容会相应调整，我会把明细列清楚给您确认，"
        "避免后期理解偏差。"
    ),
    "焦虑催结果": (
        "院校审核周期一般是 4-8 周，部分学校更久。目前材料已齐全，进度我这边会盯着，"
        "一有邮件第一时间同步您。您不用重复催，我会按节点主动汇报。"
    ),
    "保录询问": (
        "这里需要如实说明：我们不做保录、保过，也没有内推渠道。录取由学校独立审核，"
        "任何机构承诺保录都属于违规宣传。我们能做的是把选校梯度排合理、把材料和文书做到位，"
        "尽可能提高竞争力，这个流程我会全程跟您对齐。"
    ),
    "默认": (
        "您的情况我先记录一下，稍后结合院校库给您做一版三档选校方案，"
        "所有录取要求都以学校官网为准，我会标注每所学校的风险点。"
    ),
}


def detect_intent(question: str) -> str:
    low = (question or "").lower()
    for intent, words in INTENT_RULES.items():
        if any(w in low for w in words):
            return intent
    return "默认"


def generate_talk(question: str, student: StudentBasicInfo, ctx,
                  customer_id: str = "system") -> dict:
    intent = detect_intent(question)

    # 从内控库取该场景的合规话术模板
    chunks = ctx.rag.search("compliance", f"{intent} 话术模板", top_k=5, rerank_top=3)
    templates = "\n".join(c.content for c in chunks) if chunks else ""
    used_templates = [c.source_info.get("source_id") for c in chunks]

    fallback = COMPLIANT_TEMPLATES.get(intent, COMPLIANT_TEMPLATES["默认"])
    prompt = COMPLIANT_TALK_PROMPT.format(
        question=question, student=str(student.to_prompt_dict()),
        templates=templates or "（无模板，按合规原则自行组织）")
    text = ctx.llm.text(prompt, fallback=fallback, tier="small", customer_id=customer_id)

    # 生成结果必须过护栏；高危直接换成合规提示
    verdict = ctx.safety.check(text, customer_id=customer_id)
    if verdict.blocked:
        text = COMPLIANT_TEMPLATES["默认"]
        verdict = ctx.safety.check(text, customer_id=customer_id)

    return {
        "question": question,
        "intent": intent,
        "text": text,
        "templates_used": used_templates,
        "safety_level": verdict.level,
        "safety_blocked": verdict.blocked,
    }
