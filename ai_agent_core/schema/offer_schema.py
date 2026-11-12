"""二期：Cond Offer 解析结构体。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class CondCondition(BaseModel):
    cond_type: str = ""                # 均分 / 语言 / GRE / 毕业证 / 押金
    require_value: str = ""
    current_student_value: str = ""
    gap: str = ""
    reach_risk: str = "低"             # 低 / 中 / 高
    improve_suggest: str = ""


class OfferPolicyInfo(BaseModel):
    deposit_amount: str = ""
    deposit_refund_rule: str = ""
    cas_material_list: list[str] = Field(default_factory=list)
    unconditional_deadline: str = ""
    language_course_deadline: str = ""
    policy_conflict: str = ""


class OfferFullOutput(BaseModel):
    school_name: str = ""
    major: str = ""
    intake: str = ""
    is_conditional: bool = True
    cond_list: list[CondCondition] = Field(default_factory=list)
    policy_info: OfferPolicyInfo = Field(default_factory=OfferPolicyInfo)
    cas_time_timeline: list[str] = Field(default_factory=list)
    overall_risk: str = "中"
    raw_extract: dict = Field(default_factory=dict)
