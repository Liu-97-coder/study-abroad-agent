"""面试模拟结构体。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class InterviewQuestion(BaseModel):
    qid: str
    question: str
    category: str = "通用"          # 动机 / 学术 / 实习 / 职业 / 行为 / 团队 / 思辨 / 院校 / 收尾
    major: str = "通用"
    country: str = "通用"
    difficulty: str = "基础"
    focus: str = ""                # 考察点
    hints: str = ""                # 参考要点（顾问看的，学生答题时默认折叠）
    source_id: str = ""


class AnswerScore(BaseModel):
    qid: str
    total: float = 0.0
    dimensions: dict[str, float] = Field(default_factory=dict)
    feedback: list[str] = Field(default_factory=list)
    suggestion: str = ""
    answer_preview: str = ""


class InterviewSession(BaseModel):
    session_id: str
    customer_id: str = ""
    target: str = ""                        # 英国·硕士·计算机
    questions: list[InterviewQuestion] = Field(default_factory=list)
    answers: list[AnswerScore] = Field(default_factory=list)
    report: str = ""
    avg_score: float = 0.0
    created_at: str = ""
