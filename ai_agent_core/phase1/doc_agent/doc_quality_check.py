"""AI 文书质检（文书 Agent 步骤 5）。

六个维度，两条路：
- 规则路：模板化词、空话密度、专业关键词覆盖、段落结构、量化密度 —— 全部可解释
- LLM 路：把文书 + 真实经历一起给模型，让它判断"有没有编造""像不像模板"

输出 0-100 总分 + 分项 + 可执行建议。低于 60 分直接打风险标签，禁止直接交付客户。
"""
from __future__ import annotations

from ...prompt.quality_prompt import DOC_QUALITY_PROMPT
from ...schema.document_schema import StudentExperience
from ...schema.student_schema import StudentBasicInfo
from ...utils.text_clean import keyword_coverage, split_sentences

TEMPLATE_PHRASES = [
    "从小对", "一直以来", "随着社会的发展", "在当今", "贵校", "贵专业", "我认为",
    "我相信", "综上所述", "不可否认", "众所周知", "自从我", "在我的成长过程中",
]
HOLLOW_WORDS = [
    "优秀", "出色", "丰富", "扎实", "卓越", "深刻", "极大地", "充分", "高度", "非常",
    "热爱", "充满热情", "综合素质", "全面提升", "不断努力", "追求卓越", "独特", "宝贵",
]
CONNECTIVES = ["因此", "然而", "此外", "同时", "具体而言", "例如", "所以", "并且", "但是", "其中"]


def _major_keywords(context_text: str) -> list[str]:
    """从 RAG 课程素材里抽高频专业词做"匹配度"分母。"""
    import re

    words = re.findall(r"[A-Za-z][A-Za-z\-]{3,}|[\u4e00-\u9fa5]{2,6}", context_text)
    stop = {"课程", "专业", "学生", "培养", "目标", "通过", "以及", "包括", "可以", "我们", "进行"}
    freq: dict[str, int] = {}
    for w in words:
        if w in stop or len(w) < 2:
            continue
        freq[w] = freq.get(w, 0) + 1
    return [w for w, _ in sorted(freq.items(), key=lambda kv: kv[1], reverse=True)[:20]]


def check_by_rules(doc: str, experiences: list[StudentExperience],
                   major_context: str = "") -> dict:
    doc = doc or ""
    sentences = split_sentences(doc)
    total_chars = max(len(doc), 1)

    template_hits = sum(doc.count(p) for p in TEMPLATE_PHRASES)
    template_score = min(100.0, template_hits * 22.0)          # 越高越糟

    hollow_hits = sum(len(__import__("re").findall(w, doc)) for w in HOLLOW_WORDS)
    hollow_score = min(100.0, hollow_hits / max(len(sentences), 1) * 45.0)  # 越高越糟

    exp_tokens = [w for e in experiences for w in (e.org, e.title) if w]
    authenticity = keyword_coverage(exp_tokens[:12], doc) * 100 if exp_tokens else 40.0

    major_kw = _major_keywords(major_context)
    major_match = keyword_coverage(major_kw[:12], doc) * 100 if major_kw else 45.0

    paragraphs = [p for p in doc.split("\n\n") if len(p.strip()) > 30]
    connectives = sum(1 for c in CONNECTIVES if c in doc)
    logic = min(100.0, 40 + len(paragraphs) * 6 + connectives * 5)

    import re

    quant = len(re.findall(r"\d+(?:\.\d+)?%?|\d+\s*(?:万|人|次|项|篇)", doc))
    grammar = 55 + min(35, quant * 6)
    if doc and not re.search(r"[.!?。！？]", doc):
        grammar -= 20

    dims = {
        "真实匹配度": round(authenticity, 1),
        "专业匹配度": round(major_match, 1),
        "模板化程度": round(template_score, 1),
        "空话冗余度": round(hollow_score, 1),
        "逻辑连贯性": round(logic, 1),
        "语法地道性": round(max(0.0, grammar), 1),
    }
    total = round(
        dims["真实匹配度"] * 0.25
        + dims["专业匹配度"] * 0.2
        + (100 - dims["模板化程度"]) * 0.2
        + (100 - dims["空话冗余度"]) * 0.15
        + dims["逻辑连贯性"] * 0.1
        + dims["语法地道性"] * 0.1, 1)

    comments, suggestions = [], []
    if dims["模板化程度"] > 40:
        comments.append("检测到通用套话句式，模板化偏高")
        suggestions.append("删除「从小对/随着社会发展」类开头，换成一个具体场景")
    if dims["空话冗余度"] > 40:
        comments.append("形容词堆砌偏多，缺少事实支撑")
        suggestions.append("每个形容词后面补一个数字或事件，否则删掉")
    if dims["真实匹配度"] < 50:
        comments.append("文书与经历清单对应度低，可能存在泛泛而谈")
        suggestions.append("逐段核对：每段是否都能指到一条具体经历")
    if dims["专业匹配度"] < 50:
        comments.append("与目标专业课程关联弱")
        suggestions.append("补 2-3 门目标专业课程名与课程项目，说明匹配理由")
    if not comments:
        comments.append("六维均未触发明显问题")
    if not suggestions:
        suggestions.append("建议人工复核数字与经历时间线一致性")

    return {"total": total, "dimensions": dims, "comments": comments,
            "suggestions": suggestions}


def check_document(doc: str, student: StudentBasicInfo,
                   experiences: list[StudentExperience], major_context: str, ctx,
                   customer_id: str = "system") -> dict:
    rule_result = check_by_rules(doc, experiences, major_context)

    if ctx.llm.available:
        exp_text = "\n".join(f"- {e.title}@{e.org}: {e.content[:120]}" for e in experiences)
        prompt = DOC_QUALITY_PROMPT.format(
            target_major=student.target_major or "", experiences=exp_text, doc=doc[:6000])
        llm_result = ctx.llm.json(prompt, fallback=None, tier="big", customer_id=customer_id)
        if isinstance(llm_result, dict) and "total" in llm_result:
            merged = dict(rule_result)
            merged.update({k: llm_result[k] for k in ("dimensions", "comments", "suggestions")
                           if k in llm_result})
            merged["total"] = float(llm_result.get("total", rule_result["total"]))
            merged["source"] = "llm"
            return merged

    rule_result["source"] = "rule"
    return rule_result
