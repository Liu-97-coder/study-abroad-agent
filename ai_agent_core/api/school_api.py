"""选校模块接口（一期）。

POST /api/school/extract  学生背景抽取
POST /api/school/match    三档选校清单
POST /api/school/report   背景评估报告
POST /api/school/talk     合规咨询话术
POST /api/school/summary  咨询纪要
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..phase1.school_agent.chat_summary import summarize
from ..phase1.school_agent.report_generator import generate_report
from ..phase1.school_agent.school_filter import filter_schools
from ..phase1.school_agent.school_score import split_into_three
from ..phase1.school_agent.student_extract import build_followup, extract_student
from ..phase1.school_agent.talk_generator import generate_talk
from ..schema.common_schema import ApiResponse
from ..schema.school_schema import SchoolResult
from .deps import apply_chat, get_ctx, load_state, persist, rate_limit

router = APIRouter(prefix="/api/school", tags=["一期·选校"])


class ChatRequest(BaseModel):
    customer_id: str
    chat_text: str = ""
    customer_questions: str = Field(default="", description="客户原话，用于话术生成")
    name: str = ""


class TalkRequest(BaseModel):
    customer_id: str
    question: str
    chat_text: str = ""


def _student_of(state, chat_text: str):
    ctx = get_ctx()
    existing = {k: v for k, v in state.student_info.items() if k != "raw_chat"}
    student = extract_student(chat_text, ctx=ctx, existing=existing,
                              customer_id=state.customer_id)
    state.student_info.update(student.model_dump())
    return student


@router.post("/extract", response_model=ApiResponse)
def extract(payload: ChatRequest, _: None = Depends(rate_limit)):
    ctx = get_ctx()
    student = extract_student(payload.chat_text, ctx=ctx, customer_id=payload.customer_id)
    state = load_state(payload.customer_id, payload.name)
    state.student_info = {**state.student_info, **student.model_dump()}
    persist(state)
    return ApiResponse.ok({
        "student": student.model_dump(),
        "risk_tags": student.risk_tags,
        "missing_info": student.missing_info,
        "followup": build_followup(student, ctx, payload.customer_id),
    })


@router.post("/match", response_model=ApiResponse)
def match(payload: ChatRequest, _: None = Depends(rate_limit)):
    ctx = get_ctx()
    state = load_state(payload.customer_id, payload.name)
    student = _student_of(state, payload.chat_text or str(state.student_info.get("raw_chat", "")))
    state.student_info.update(student.model_dump())

    filtered = filter_schools(ctx.rag, student)
    buckets = split_into_three(filtered.candidates, student)
    result = SchoolResult(sprint_list=buckets["冲刺"], match_list=buckets["匹配"],
                          safe_list=buckets["保底"], filtered_out=filtered.dropped,
                          sources=[c["source_id"] for c in filtered.candidates])
    state.agent_outputs["school"] = {"student": student.model_dump(), "result": result.model_dump()}
    persist(state)
    return ApiResponse.ok({
        "student": student.model_dump(),
        "result": result.model_dump(),
        "warnings": filtered.warnings,
        "counts": {k: len(v) for k, v in buckets.items()},
    })


@router.post("/report", response_model=ApiResponse)
def report(payload: ChatRequest, _: None = Depends(rate_limit)):
    ctx = get_ctx()
    state = load_state(payload.customer_id, payload.name)
    cached = state.agent_outputs.get("school") or {}
    if not cached.get("result"):
        return ApiResponse.fail("请先调用 /api/school/match 生成选校结果", code=400)
    student = extract_student("", ctx=ctx, existing=state.student_info,
                              customer_id=payload.customer_id)
    result = SchoolResult(**cached["result"])
    data = generate_report(student, result, ctx, payload.customer_id)
    cached["report"] = data
    state.agent_outputs["school"] = cached
    persist(state)
    return ApiResponse.ok(data)


@router.post("/talk", response_model=ApiResponse)
def talk(payload: TalkRequest, _: None = Depends(rate_limit)):
    ctx = get_ctx()
    state = load_state(payload.customer_id)
    student = extract_student(payload.chat_text, ctx=ctx, existing=state.student_info,
                              customer_id=payload.customer_id)
    data = generate_talk(payload.question, student, ctx, payload.customer_id)
    persist(state)
    return ApiResponse.ok(data)


@router.post("/summary", response_model=ApiResponse)
def summary(payload: ChatRequest, _: None = Depends(rate_limit)):
    ctx = get_ctx()
    state = load_state(payload.customer_id, payload.name)
    student = extract_student(payload.chat_text or str(state.student_info.get("raw_chat", "")),
                              ctx=ctx, existing=state.student_info,
                              customer_id=payload.customer_id)
    data = summarize(payload.chat_text or str(state.student_info.get("raw_chat", "")),
                     student, ctx, payload.customer_id)
    return ApiResponse.ok(data)
