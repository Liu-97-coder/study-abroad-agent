"""签证时间线规划（签证 Agent 步骤 3）。

从「计划入境日」倒推：出签 → 递签 → 录指纹 → 公证 → 体检 → 资金冻结。
预留周期 < 45 天高危、< 30 天加急、< 15 天极度危险。
"""
from __future__ import annotations

from ...schema.visa_schema import VisaTimeNode
from ...utils.date_utils import add_days, days_until

# 各环节耗时（天）：(节点, 耗时, 说明)
NODES = [
    ("资金冻结/存款达标", 28, "英国需存满 28 天，澳洲 6 个月"),
    ("亲属关系公证", 21, "父母出资才需要，公证处办理周期 2-3 周"),
    ("肺结核体检", 7, "英国/澳洲需要，指定诊所预约"),
    ("在线填表与预约", 3, "预约录指纹需抢号"),
    ("递交签证", 1, "材料齐全后当天可递"),
    ("出签等待", 21, "标准审理 3 周，高峰期更久"),
]
TOTAL_DAYS = sum(days for _, days, _ in NODES)


def plan_timeline(arrival_date: str, cas_date: str = "", country: str = "英国") -> dict:
    nodes = [VisaTimeNode(node_name=name, cycle_days=cycle, risk_warn=remark)
             for name, cycle, remark in NODES]

    # 从入境日往前逐个扣减各环节耗时，得到每个节点的建议完成日期
    cursor = arrival_date
    for idx in range(len(nodes) - 1, -1, -1):
        nodes[idx].suggest_finish_date = add_days(cursor, -nodes[idx].cycle_days) if cursor else ""
        cursor = nodes[idx].suggest_finish_date

    left = days_until(arrival_date)
    risk, warn = "低", ""
    if left is not None:
        if left < 15:
            risk, warn = "高", f"距计划入境仅 {left} 天，签证流程几乎不可能完成，建议延期入学"
        elif left < 30:
            risk, warn = "高", f"距计划入境 {left} 天，需加急：优先约体检与公证"
        elif left < 45:
            risk, warn = "中", f"距计划入境 {left} 天，预留偏紧，禁止任何环节延期"

    if cas_date and (days_until(cas_date) or 0) > 0:
        nodes.insert(0, VisaTimeNode(node_name="等待 CAS 下发", cycle_days=21,
                                     suggest_finish_date=cas_date,
                                     risk_warn="CAS 未到无法递签，需持续催学校"))

    todo = ["确认存款已满足存期要求，期间不动用这笔钱"]
    if risk == "高":
        todo.append("立即启动公证与体检预约（周期最长）")
    if risk in {"高", "中"}:
        todo.append("同步催学校出 CAS，并准备递签全套材料")
    else:
        todo.append("按节点表推进，每周更新一次材料状态")
    if country in {"英国", "澳洲"}:
        todo.append(f"{country} 需预约肺结核指定诊所，先查可预约名额")

    return {"nodes": nodes, "risk": risk, "warn": warn, "todo": todo,
            "total_days": TOTAL_DAYS, "days_left": left}
