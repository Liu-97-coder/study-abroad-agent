"""选校结果结构体（对应文档 school_schema.py）。

注意 level_type 的语义：reach_score 越高 = 越难录取 = 越靠"冲刺"，
这是原文档 75-100 冲刺 / 50-75 匹配 / 0-50 保底 的划定方式，
等价于"录取难度指数"，报告里要写清楚，避免顾问误读。
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class SchoolItem(BaseModel):
    school_name: str
    major_name: str
    country: str = ""
    level_type: str = "匹配"          # 冲刺 / 匹配 / 保底
    gpa_require: str = ""
    lang_require: str = ""
    other_require: str = ""
    deadline: str = ""
    days_left: int | None = None
    risk_point: str = ""
    match_score: float = 0.0           # 0-100 录取难度指数
    score_detail: dict = Field(default_factory=dict)
    source_id: str = ""                # 溯源：这条数据来自知识库哪一条


class SchoolResult(BaseModel):
    sprint_list: list[SchoolItem] = Field(default_factory=list)
    match_list: list[SchoolItem] = Field(default_factory=list)
    safe_list: list[SchoolItem] = Field(default_factory=list)
    student_summary: str = ""
    apply_suggest: str = ""
    overall_risk: str = "中"
    filtered_out: list[dict] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)

    def all_items(self) -> list[SchoolItem]:
        return self.sprint_list + self.match_list + self.safe_list
