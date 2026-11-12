"""二期：材料催收 & 校验结构体。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class MaterialItem(BaseModel):
    material_name: str
    is_required: bool = True
    submit_deadline: str | None = None
    check_standard: str = ""
    remark: str = ""
    category: str = "基础材料"          # 基础材料 / 学术材料 / 签证材料 / 资金材料


class MaterialCheckRisk(BaseModel):
    risk_level: str = "低"             # 低 / 中 / 高
    risk_desc: str = ""
    fix_suggest: str = ""
    material_name: str = ""


class MaterialCheckResult(BaseModel):
    material_name: str
    pass_flag: bool = True
    risk_list: list[MaterialCheckRisk] = Field(default_factory=list)
    upload_file_id: str | None = None
    extracted: dict = Field(default_factory=dict)


class MaterialFullOutput(BaseModel):
    material_list: list[MaterialItem] = Field(default_factory=list)
    uploaded_check_results: list[MaterialCheckResult] = Field(default_factory=list)
    missing_materials: list[str] = Field(default_factory=list)
    all_risk: list[MaterialCheckRisk] = Field(default_factory=list)
    todo_task_list: list[str] = Field(default_factory=list)
    notice_text: str = ""
