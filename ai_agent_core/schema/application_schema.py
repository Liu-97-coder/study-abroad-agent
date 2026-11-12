"""二期：网申监控 & 院校邮件结构体。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class FormCheckError(BaseModel):
    field_name: str
    error_msg: str
    suggest_value: str | None = None
    level: str = "低级错误"            # 低级错误 / 风险提示


class MailInfo(BaseModel):
    mail_intent: str = "其他"          # 补件通知 / 面试邀请 / 押金提醒 / Offer / 拒信WL
    source_subject: str = ""
    deadline: str | None = None
    need_supplement: list[str] = Field(default_factory=list)
    extra_notice: str = ""
    confidence: float = 0.8


class RefereeRemindTask(BaseModel):
    referee_email: str
    send_link_date: str
    days_waiting: int = 0
    remind_content: str = ""
    is_submitted: bool = False


class ApplicationOutput(BaseModel):
    form_error_list: list[FormCheckError] = Field(default_factory=list)
    mail_info_list: list[MailInfo] = Field(default_factory=list)
    deadline_warn_list: list[dict] = Field(default_factory=list)
    referee_todo: list[RefereeRemindTask] = Field(default_factory=list)
