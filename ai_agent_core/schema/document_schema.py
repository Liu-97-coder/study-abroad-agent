"""文书结构体（对应文档 document_schema.py）。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class StudentExperience(BaseModel):
    title: str = ""
    org: str = ""
    time: str = ""
    content: str = ""
    highlight: str = ""
    skills: list[str] = Field(default_factory=list)
    kind: str = "internship"          # education / internship / research / award / project


class QualityReport(BaseModel):
    total: float = 0.0
    dimensions: dict[str, float] = Field(default_factory=dict)
    comments: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    source: str = "rule"              # rule / llm


class DocResult(BaseModel):
    cv_content: str = ""
    ps_content: str = ""
    ref1_content: str = ""
    ref2_content: str = ""
    quality_score: float = 0.0
    quality_report: str = ""
    version_id: str = ""
    create_time: str = ""
    major_family: str = ""
    sources: list[str] = Field(default_factory=list)
