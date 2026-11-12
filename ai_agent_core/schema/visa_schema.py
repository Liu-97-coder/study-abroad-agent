"""二期：签证材料与资金风险结构体。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class FundRiskItem(BaseModel):
    risk_tag: str = ""
    risk_level: str = "低"
    reason: str = ""
    fix_plan: str = ""


class VisaMaterialItem(BaseModel):
    material_name: str
    need_notarize: bool = False
    valid_days: int = 0
    is_required: bool = True
    order: int = 1
    remark: str = ""


class VisaTimeNode(BaseModel):
    node_name: str
    suggest_finish_date: str = ""
    cycle_days: int = 0
    risk_warn: str = ""


class VisaFullOutput(BaseModel):
    target_country: str = ""
    fund_total: float = 0.0
    fund_currency: str = "CNY"
    fund_risk_list: list[FundRiskItem] = Field(default_factory=list)
    visa_material_list: list[VisaMaterialItem] = Field(default_factory=list)
    time_timeline: list[VisaTimeNode] = Field(default_factory=list)
    missing_materials: list[str] = Field(default_factory=list)
    todo_task_list: list[str] = Field(default_factory=list)
    overall_risk: str = "低"
