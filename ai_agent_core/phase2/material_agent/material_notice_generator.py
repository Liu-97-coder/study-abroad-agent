"""阶梯催收话术（材料 Agent 步骤 2）：初次 / 逾期 3 天 / 逾期 7 天。"""
from __future__ import annotations

from ...prompt.material_prompt import MATERIAL_NOTICE_PROMPT


def tier_of(days_overdue: int) -> str:
    if days_overdue >= 7:
        return "加急"
    if days_overdue >= 3:
        return "逾期"
    return "初次"


def generate_notice(missing: list[str], days_overdue: int, country: str = "",
                    ctx=None, customer_id: str = "system") -> dict:
    tier = tier_of(days_overdue)
    names = "、".join(missing) if missing else "（无缺失）"

    student_text = {
        "初次": f"同学你好～你的申请材料还差这几项：{names}。这些是网申必备件，"
                f"建议本周内准备好发我，我这边同步帮你检查格式，避免递交时被打回。",
        "逾期": f"同学，材料已经超期 {days_overdue} 天了：{names}。"
                f"再不提交会影响递交节奏，能今天先拍照发我吗？我先帮你过一遍能不能用。",
        "加急": f"同学，{names} 已经超期 {days_overdue} 天，再拖下去可能赶不上这一轮审核。"
                f"请今天务必处理，需要我们协助联系学校开证明的话我现在就安排。",
    }[tier]

    advisor_note = {
        "初次": f"首次催收：缺 {names}，已告知用途与截止。",
        "逾期": f"逾期 {days_overdue} 天：缺 {names}，需顾问电话跟进。",
        "加急": f"高危逾期 {days_overdue} 天：缺 {names}，建议升级主管，评估是否顺延申请轮次。",
    }[tier]

    if ctx is not None and ctx.llm.available:
        prompt = MATERIAL_NOTICE_PROMPT.format(materials=names, days=days_overdue,
                                              country=country or "未指定")
        data = ctx.llm.json(prompt, fallback=None, tier="small", customer_id=customer_id)
        if isinstance(data, dict):
            student_text = data.get("student_text", student_text)
            advisor_note = data.get("advisor_note", advisor_note)

    return {"tier": tier, "student_text": student_text, "advisor_note": advisor_note}
