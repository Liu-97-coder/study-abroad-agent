"""CAS 材料清单与办理时间线（Offer Agent 步骤 4）。

时间线必须倒推：学校 CAS 下发周期浮动（2-6 周），签证办理又要 3-4 周，
所以"换无条件截止"往前一减，才知道现在该催哪一步。
"""
from __future__ import annotations

from ...schema.offer_schema import OfferPolicyInfo
from ...utils.date_utils import add_days, days_until

CAS_CYCLE_DAYS = 21
VISA_CYCLE_DAYS = 21
BUFFER_DAYS = 14


def build_plan(policy: OfferPolicyInfo, intake_date: str = "") -> dict:
    uncon = policy.unconditional_deadline or ""
    nodes = []
    if uncon:
        nodes = [
            f"语言/均分出分：最晚 {add_days(uncon, -45)} 前拿到达标成绩",
            f"缴纳押金：最晚 {add_days(uncon, -30)} 前完成（押金不退的院校尤其要确认）",
            f"提交 CAS 材料：最晚 {add_days(uncon, -25)} 前提交全套材料",
            f"CAS 下发：预计 {add_days(uncon, -4)} 前后（周期约 {CAS_CYCLE_DAYS} 天）",
            f"递交签证：CAS 到手后 3 天内，即 {add_days(uncon, 1)} 前",
            f"出签：预计 {add_days(uncon, VISA_CYCLE_DAYS)} 前后，预留 {BUFFER_DAYS} 天缓冲",
        ]
    else:
        nodes = ["院校库缺少换无条件截止日期，需顾问按官网补录后生成时间线"]

    left = days_until(uncon)
    risk = ""
    if left is not None:
        if left <= 20:
            risk = f"换无条件截止仅剩 {left} 天，全部节点必须加急"
        elif left <= 30:
            risk = f"换无条件截止剩 {left} 天，押金与 CAS 材料需今日启动"

    if intake_date:
        nodes.append(f"入境前 30 天：办理体检/住宿/机票（目标入境 {intake_date}）")

    return {
        "materials": policy.cas_material_list or ["Offer 原件", "押金凭证", "护照", "成绩单"],
        "timeline": nodes,
        "risk": risk,
        "days_to_uncon": left,
    }
