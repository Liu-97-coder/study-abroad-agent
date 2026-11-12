"""面试模拟接口。

POST /api/interview/start    生成一份模拟面试卷
POST /api/interview/answer   提交单题回答，返回五维评分
GET  /api/interview/report   复盘报告
GET  /api/interview/sessions 该客户的历史场次
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..phase2.interview_agent.answer_scorer import build_report
from ..phase2.interview_agent.interview_agent_node import answer_question, start_session
from ..schema.common_schema import ApiResponse
from ..schema.interview_schema import InterviewSession
from ..schema.student_schema import StudentBasicInfo
from .deps import get_ctx, load_state, persist, rate_limit

router = APIRouter(prefix="/api/interview", tags=["面试模拟"])


class StartRequest(BaseModel):
    customer_id: str
    count: int = 6


class AnswerRequest(BaseModel):
    session_id: str
    qid: str
    answer: str


def _student(state) -> StudentBasicInfo:
    return StudentBasicInfo(**{k: v for k, v in state.student_info.items()
                               if k in StudentBasicInfo.model_fields})


@router.post("/start", response_model=ApiResponse)
def start(payload: StartRequest, _: None = Depends(rate_limit)):
    ctx = get_ctx()
    state = load_state(payload.customer_id)
    student = _student(state)
    session = start_session(payload.customer_id, student, ctx,
                            count=max(3, min(10, payload.count)))
    ctx.storage.save_interview(session)
    state.agent_outputs["interview"] = session.model_dump()
    state.student_info["interview_requested"] = True
    persist(state)
    ctx.logger.event("interview", "start", customer_id=payload.customer_id,
                     session_id=session.session_id, count=len(session.questions))
    return ApiResponse.ok(session.model_dump())


@router.post("/answer", response_model=ApiResponse)
def answer(payload: AnswerRequest, _: None = Depends(rate_limit)):
    ctx = get_ctx()
    data = ctx.storage.load_interview(payload.session_id)
    if not data:
        return ApiResponse.fail("场次不存在", code=404)
    session = InterviewSession(**data)
    try:
        session = answer_question(session, payload.qid, payload.answer, ctx,
                                  session.customer_id)
    except ValueError as exc:
        return ApiResponse.fail(str(exc), code=400)

    ctx.storage.save_interview(session)
    state = load_state(session.customer_id)
    state.agent_outputs["interview"] = session.model_dump()
    persist(state)
    latest = next(a for a in session.answers if a.qid == payload.qid)
    return ApiResponse.ok({
        "score": latest.model_dump(),
        "avg_score": session.avg_score,
        "answered": len(session.answers),
        "total": len(session.questions),
    })


@router.get("/report", response_model=ApiResponse)
def report(session_id: str):
    ctx = get_ctx()
    data = ctx.storage.load_interview(session_id)
    if not data:
        return ApiResponse.fail("场次不存在", code=404)
    session = InterviewSession(**data)
    session.report = session.report or build_report(session)
    return ApiResponse.ok({"session_id": session.session_id, "avg_score": session.avg_score,
                           "answered": len(session.answers), "total": len(session.questions),
                           "report": session.report})


@router.get("/sessions", response_model=ApiResponse)
def sessions(customer_id: str):
    return ApiResponse.ok(get_ctx().storage.list_interviews(customer_id))
