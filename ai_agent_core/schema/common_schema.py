"""通用返回结构：接口响应、检索片段、安全判定、待办。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ApiResponse(BaseModel):
    code: int = 0
    message: str = "ok"
    data: Any = None

    @classmethod
    def ok(cls, data: Any = None, message: str = "ok") -> "ApiResponse":
        return cls(code=0, message=message, data=data)

    @classmethod
    def fail(cls, message: str, code: int = 500) -> "ApiResponse":
        return cls(code=code, message=message, data=None)


class RetrievedChunk(BaseModel):
    """检索片段：必须带 source_info，这是防幻觉的命门（任务 1.6）。"""
    content: str
    metadata: dict = Field(default_factory=dict)
    source_info: dict = Field(default_factory=dict)
    score: float = 0.0

    @property
    def source_id(self) -> str:
        return str(self.source_info.get("source_id", ""))


class SafetyVerdict(BaseModel):
    level: str = "low"                 # low / medium / high
    blocked: bool = False
    hits: list[str] = Field(default_factory=list)
    reason: str = ""
    sanitized_text: str = ""


class TaskItem(BaseModel):
    task_id: str = ""
    customer_id: str = ""
    title: str = ""
    level: str = "普通"                # 紧急 / 普通 / 延期风险
    owner: str = "顾问"
    due_date: str = ""
    source: str = ""                   # 由哪个 Agent 生成
    status: str = "open"
