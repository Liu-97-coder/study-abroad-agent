"""签证资金材料 AI 风险推理（签证 Agent 步骤 2，二期核心难点）。

四个判定维度，全部可解释：
1. 余额是否覆盖 学费 + 生活费
2. 存期是否满足法定时长（英国 28 天 / 澳洲 6 个月 / 加拿大 4 个月）
3. 是否存在大额短期入账（拒签第一诱因）
4. 流水是否连续（断档 > 60 天要被追问）

规则给出 level 与整改方案；LLM 只在有真实模型时补充话术，不改判定。
"""
from __future__ import annotations

from ...prompt.fund_risk_prompt import FUND_RISK_ANALYZE_PROMPT
from ...schema.visa_schema import FundRiskItem
from ...utils.date_utils import days_until

FUND_REQUIREMENT = {"英国": 350000, "澳洲": 300000, "香港": 200000, "加拿大": 250000,
                    "新加坡": 250000, "美国": 400000, "欧洲": 200000}
DEPOSIT_DAYS = {"英国": 28, "澳洲": 180, "加拿大": 120}
LARGE_INFLOW_RATIO = 0.4      # 单笔占总额 40% 以上视为大额
LARGE_INFLOW_WINDOW = 30      # 且发生在最近 30 天内
GAP_DAYS = 60


def analyze_fund(fund_data: dict, country: str, ctx=None,
                 customer_id: str = "system") -> tuple[list[FundRiskItem], float, str]:
    risks: list[FundRiskItem] = []
    amount = float(fund_data.get("amount") or 0)
    need = FUND_REQUIREMENT.get(country, 300000)

    if amount <= 0:
        risks.append(FundRiskItem(risk_tag="无资金材料", risk_level="高",
                                  reason="未识别到存款金额",
                                  fix_plan="补传存款证明与近 6 个月流水"))
    elif amount < need:
        risks.append(FundRiskItem(
            risk_tag="金额不足", risk_level="高",
            reason=f"当前 {amount:,.0f} 元，{country} 建议不低于 {need:,.0f} 元",
            fix_plan=f"增加存款 {need - amount:,.0f} 元，或用父母资金合并计算并出具出资函"))

    days_need = DEPOSIT_DAYS.get(country, 0)
    have_days = fund_data.get("deposit_days")
    deposit_date = fund_data.get("deposit_date")
    if days_need:
        if have_days is None and deposit_date:
            left = days_until(deposit_date)
            have_days = abs(left) if left is not None else None
        if have_days is None:
            risks.append(FundRiskItem(risk_tag="存期未知", risk_level="中",
                                      reason=f"{country} 要求存满 {days_need} 天",
                                      fix_plan="开具带存入日期的存款证明，按 28 天规则倒排递交日"))
        elif have_days < days_need:
            risks.append(FundRiskItem(risk_tag="存期不足", risk_level="高",
                                      reason=f"已存 {have_days} 天，要求 {days_need} 天",
                                      fix_plan=f"再存 {days_need - have_days} 天后再递签，期间不要动这笔钱"))

    for inflow in fund_data.get("large_inflows") or []:
        value = float(inflow.get("amount") or 0)
        recent = inflow.get("days_ago")
        if amount and value / amount >= LARGE_INFLOW_RATIO and (recent is None or recent <= LARGE_INFLOW_WINDOW):
            risks.append(FundRiskItem(
                risk_tag="大额临存", risk_level="高",
                reason=f"近 {recent if recent is not None else '?'} 天入账 {value:,.0f} 元，占比 "
                       f"{value / amount:.0%}，易被质疑资金来源",
                fix_plan="提供资金来源证明（工资/理财赎回/房产交易），或延长存期稀释嫌疑"))

    gaps = fund_data.get("statement_gaps") or []
    for gap in gaps:
        if float(gap) > GAP_DAYS:
            risks.append(FundRiskItem(risk_tag="流水断档", risk_level="中",
                                      reason=f"流水出现 {gap} 天无交易记录",
                                      fix_plan="补充该期间其他账户流水或说明原因（如出国/休学）"))

    level = "高" if any(r.risk_level == "高" for r in risks) else (
        "中" if any(r.risk_level == "中" for r in risks) else "低")

    if ctx is not None and ctx.llm.available and risks:
        prompt = FUND_RISK_ANALYZE_PROMPT.format(
            country=country, fund_data=str(fund_data)[:1500], context="（规则引擎已给出判定）")
        extra = ctx.llm.json(prompt, fallback=None, tier="big", customer_id=customer_id)
        if isinstance(extra, list):
            for item in extra:
                if isinstance(item, dict) and item.get("risk_tag"):
                    risks.append(FundRiskItem(risk_tag=str(item["risk_tag"]),
                                              risk_level=str(item.get("risk_level", "中")),
                                              reason=str(item.get("reason", ""))[:200],
                                              fix_plan=str(item.get("fix_plan", ""))[:200]))
    return risks, amount, level
