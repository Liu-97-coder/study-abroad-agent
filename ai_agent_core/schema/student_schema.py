"""学生档案结构体（对应文档 student_schema.py）。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class StudentBasicInfo(BaseModel):
    # 院校背景
    school_level: str | None = None       # 985 / 211 / 双一流 / 普通本科 / 海外
    school_name: str | None = None
    major: str | None = None
    grade: str | None = None              # 大三 / 已毕业
    # 成绩
    gpa: float | None = None
    gpa_scale: float | None = 4.0
    average_score: float | None = None
    # 语言
    ielts: float | None = None
    toefl: int | None = None
    gre: int | None = None
    gmat: int | None = None
    # 软背景
    internship_count: int = 0
    research_count: int = 0
    award_count: int = 0
    # 申请意向
    target_country: list[str] = Field(default_factory=list)
    target_degree: str | None = None
    target_major: str | None = None
    budget: str | None = None
    intake_year: int | None = None
    intake_month: int | None = None
    # 风险 & 缺失
    risk_tags: list[str] = Field(default_factory=list)
    missing_info: list[str] = Field(default_factory=list)

    def to_prompt_dict(self) -> dict:
        data = self.model_dump()
        data.pop("missing_info", None)
        return data
