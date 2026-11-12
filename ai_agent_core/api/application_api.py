"""网申模块接口（二期）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..phase2.app_agent.application_form_checker import check_form
from ..phase2.app_agent.deadline_watcher import from_school_result
from ..phase2.app_agent.email_extract_parser import parse_email
from ..phase2.app_agent.referee_reminder import build_reminders, needs_action
from ..schema.common_schema import ApiResponse
from ..schema.student_schema import StudentBasicInfo
from .deps import get_ctx, load_state, rate_limit

router = APIRouter(prefix="/api/application", tags=["二期·网申"])


class FormRequest(BaseModel):
    customer_id: str
    form_data: dict
    passport_text: str = ""


class MailRequest(BaseModel):
    customer_id: str
    subject: str = ""
    mail_text: str


def _student(state) -> StudentBasicInfo:
    return StudentBasicInfo(**{k: v for k, v in state.student_info.items()
                               if k in StudentBasicInfo.model_fields})


@router.post("/form-check", response_model=ApiResponse)
def form_check(payload: FormRequest, _: None = Depends(rate_limit)):
    ctx = get_ctx()
    state = load_state(payload.customer_id)
    passport = ctx.ocr.parse(text=payload.passport_text).entities if payload.passport_text else {}
    errors = check_form(payload.form_data, _student(state), passport)
    return ApiResponse.ok({"errors": [e.model_dump() for e in errors],
                           "blocked": any(e.level == "低级错误" for e in errors)})


@router.post("/parse-mail", response_model=ApiResponse)
def parse_mail(payload: MailRequest, _: None = Depends(rate_limit)):
    ctx = get_ctx()
    info = parse_email(payload.subject, payload.mail_text, ctx, payload.customer_id)
    return ApiResponse.ok(info.model_dump())


@router.get("/deadline-warn", response_model=ApiResponse)
def deadline_warn(customer_id: str):
    state = load_state(customer_id)
    result = (state.agent_outputs.get("school") or {}).get("result") or {}
    submitted = [p.get("school", "") for p in state.student_info.get("submitted_programs") or []]
    warnings = from_school_result(result, submitted)
    return ApiResponse.ok({"warnings": warnings, "count": len(warnings)})


@router.get("/referee-todo", response_model=ApiResponse)
def referee_todo(customer_id: str):
    state = load_state(customer_id)
    tasks = build_reminders(state.student_info.get("referees") or [],
                            student_name=state.customer_name or "the applicant")
    return ApiResponse.ok({"all": [t.model_dump() for t in tasks],
                           "actions": [t.model_dump() for t in needs_action(tasks)]})
