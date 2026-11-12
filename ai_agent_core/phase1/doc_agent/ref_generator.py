"""推荐信生成（文书 Agent 步骤 4）：学术导师 / 企业导师两种风格，各 2 版。"""
from __future__ import annotations

from ...prompt.doc_prompt import REF_GENERATE_PROMPT
from ...schema.document_schema import StudentExperience
from ...schema.student_schema import StudentBasicInfo

STYLES = {
    "academic": {
        "label": "学术导师",
        "focus": "学习能力、科研素养、思维逻辑",
        "relation": "课程/科研项目指导关系",
    },
    "corporate": {
        "label": "企业导师",
        "focus": "职业素养、执行力、团队协作",
        "relation": "实习期间的直属上级",
    },
}


def _render(style: str, student: StudentBasicInfo, experiences: list[StudentExperience],
            version: int) -> str:
    meta = STYLES[style]
    related = [e for e in experiences
               if (e.kind == "research" if style == "academic" else e.kind == "internship")]
    case = (related[0].highlight or related[0].content[:80]) if related else "（需补充具体事例，禁止编造）"
    tone = "更强调方法论的掌握" if version == 1 else "更强调持续进步与主动性"
    return (
        f"# Recommendation Letter（{meta['label']} · 第 {version} 版）\n\n"
        f"**推荐人身份**：{meta['label']}（待填写姓名/职称/单位）\n"
        f"**认识关系**：{meta['relation']}，时长待填\n"
        f"**评价侧重**：{meta['focus']}，本版{tone}\n\n"
        f"## 正文结构\n"
        f"1. 开篇：我是谁、如何认识该学生、认识多久\n"
        f"2. 具体事例：{case}\n"
        f"3. 能力评价：围绕{meta['focus']}给 2-3 条具体判断\n"
        f"4. 对比参照：「在我指导过的学生中处于前 X%」（需推荐人真实判断，不得代填）\n"
        f"5. 推荐结论：明确推荐 + 推荐项目方向 {student.target_major or ''}\n\n"
        f"---\n> 离线模式输出结构稿；接入 LLM 后输出两版差异化英文正文。"
        f"推荐信必须由推荐人本人确认签署，AI 只提供素材草稿。"
    )


def generate_refs(student: StudentBasicInfo, experiences: list[StudentExperience], ctx,
                  customer_id: str = "system") -> dict:
    from .experience_parse import build_experience_text

    exp_text = build_experience_text(experiences)
    outputs = {}
    for style in STYLES:
        versions = []
        for version in (1, 2):
            fallback = _render(style, student, experiences, version)
            prompt = REF_GENERATE_PROMPT.format(ref_type=STYLES[style]["label"],
                                               experiences=exp_text)
            versions.append(ctx.llm.text(prompt, fallback=fallback, tier="big",
                                         customer_id=customer_id))
        outputs[style] = versions
    return {"academic": outputs["academic"], "corporate": outputs["corporate"],
            "source": "llm" if ctx.llm.available else "rule"}
