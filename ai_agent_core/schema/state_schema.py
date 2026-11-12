"""客户全局状态：所有 Agent 共享的唯一事实来源（任务 3.1）。

设计要点（亮点 9"插件式扩展"）：字段全部给默认值，二期/三期新增 Agent
只往 agent_outputs / risk_tags 里加 key，不用改结构体，避免大规模重构。
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CustomerState(BaseModel):
    customer_id: str
    trace_id: str = ""
    stage: str = "clue"                       # 见 config.STAGES
    customer_name: str = ""
    owner: str = ""                           # 归属顾问（鉴权用）
    student_info: dict[str, Any] = Field(default_factory=dict)
    rag_context: dict[str, Any] = Field(default_factory=dict)
    agent_outputs: dict[str, Any] = Field(default_factory=dict)   # 各 Agent 输出存档
    risk_tags: list[str] = Field(default_factory=list)
    task_list: list[dict[str, Any]] = Field(default_factory=list)
    history: list[str] = Field(default_factory=list)              # 执行过的 Agent
    errors: list[str] = Field(default_factory=list)

    def add_risk(self, tag: str) -> None:
        if tag and tag not in self.risk_tags:
            self.risk_tags.append(tag)

    def add_task(self, title: str, level: str = "普通", due_date: str = "", source: str = "") -> dict:
        task = {
            "task_id": f"{self.customer_id}-{len(self.task_list) + 1}",
            "customer_id": self.customer_id,
            "title": title,
            "level": level,
            "owner": "顾问",
            "due_date": due_date,
            "source": source,
            "status": "open",
        }
        self.task_list.append(task)
        return task

    def out(self, key: str, value: Any) -> None:
        self.agent_outputs[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.agent_outputs.get(key, default)
