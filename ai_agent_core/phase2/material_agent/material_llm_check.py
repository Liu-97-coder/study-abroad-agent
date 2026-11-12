"""材料校验的 LLM 语义兜底（材料 Agent 步骤 4）。

触发条件：规则层识别字段缺失 / 文件模糊 / 结论不确定。
定位：复核，不是替代 —— 规则说"存期 20 天不够"就按规则走，LLM 只补充解释与整改建议。
"""
from __future__ import annotations

from ...prompt.material_prompt import MATERIAL_LLM_CHECK_PROMPT


def review_with_llm(material_name: str, doc, context: str, ctx,
                    customer_id: str = "system") -> list[dict] | None:
    if not ctx.llm.available:
        return None
    entities = dict(getattr(doc, "entities", {}) or {})
    entities.pop("_warnings", None)
    prompt = MATERIAL_LLM_CHECK_PROMPT.format(
        material_type=material_name,
        entities=str(entities),
        raw_text=(getattr(doc, "raw_text", "") or "")[:1500],
        context=context or "（无检索到的政策规则，仅做常识性检查，禁止编造政策）",
    )
    data = ctx.llm.json(prompt, fallback=None, tier="big", customer_id=customer_id)
    if isinstance(data, dict):
        data = data.get("risks") or data.get("data") or []
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict) and r.get("risk_level")]
    return None


def cross_check(checked: list) -> list[dict]:
    """多文件交叉校验：在读证明/成绩单/毕业证 的时间线是否自洽。"""
    problems = []
    by_name = {item.material_name: item for item in checked}
    for name, item in by_name.items():
        grad = item.extracted.get("graduation_year")
        if grad and ("在读" in name or "毕业" in name):
            problems.append({"material": name, "issue": f"文件显示毕业年份 {grad}，需与网申入学时间核对"})
    return problems
