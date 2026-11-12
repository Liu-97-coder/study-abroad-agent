"""统一调度接口：驱动 LangGraph 状态机（一期 + 二期 + 三期）。

POST /api/graph/run-consult   触发选校全流程
POST /api/graph/run-document  触发文书全流程
POST /api/graph/run-material-flow
POST /api/graph/run-application-flow
POST /api/graph/run-offer-flow
POST /api/graph/run-visa-flow
POST /api/graph/run-all       端到端演示（auto_advance=True）
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..base.graph_engine import GraphEngine, build_agents
from ..schema.common_schema import ApiResponse
from .deps import get_ctx, load_state, rate_limit

router = APIRouter(prefix="/api/graph", tags=["调度"])


class RunRequest(BaseModel):
    customer_id: str
    chat_text: str = ""
    auto_advance: bool = False
    stage: str = ""
    reset: bool = False
    # 业务数据：experiences / uploaded_files / offer_file / fund_data / emails / referees …
    payload: dict = Field(default_factory=dict)


def _engine():
    ctx = get_ctx()
    return GraphEngine(ctx, build_agents(ctx))


def _run(payload: RunRequest, default_stage: str) -> ApiResponse:
    ctx = get_ctx()
    state = load_state(payload.customer_id)
    if payload.reset:
        # 重跑整条流程：清空上一次的产出、待办、风险，避免叠加成"96 条待办"
        state.agent_outputs = {}
        state.history = []
        state.errors = []
        state.task_list = []
        state.risk_tags = []
        ctx.storage.clear_customer_artifacts(payload.customer_id)
    if payload.stage:
        state.stage = payload.stage
    elif default_stage:
        state.stage = default_stage
    if payload.payload:
        state.student_info.update(payload.payload)
    if payload.chat_text:
        state.student_info["raw_chat"] = payload.chat_text

    engine = _engine()
    before = len(state.task_list)
    state = engine.run(state, auto_advance=payload.auto_advance)
    data = {
        "customer_id": state.customer_id,
        "stage": state.stage,
        "history": state.history,
        "risk_tags": state.risk_tags,
        "new_tasks": state.task_list[before:],
        "errors": state.errors,
        "outputs": list(state.agent_outputs.keys()),
        "engine": "langgraph" if engine.app is not None else "fallback-loop",
    }
    return ApiResponse.ok(data)


@router.post("/run-consult", response_model=ApiResponse)
def run_consult(payload: RunRequest, _: None = Depends(rate_limit)):
    return _run(payload, "clue")


@router.post("/run-document", response_model=ApiResponse)
def run_document(payload: RunRequest, _: None = Depends(rate_limit)):
    return _run(payload, "document")


@router.post("/run-material-flow", response_model=ApiResponse)
def run_material(payload: RunRequest, _: None = Depends(rate_limit)):
    return _run(payload, "signed")


@router.post("/run-application-flow", response_model=ApiResponse)
def run_application(payload: RunRequest, _: None = Depends(rate_limit)):
    return _run(payload, "application")


@router.post("/run-offer-flow", response_model=ApiResponse)
def run_offer(payload: RunRequest, _: None = Depends(rate_limit)):
    return _run(payload, "offer")


@router.post("/run-visa-flow", response_model=ApiResponse)
def run_visa(payload: RunRequest, _: None = Depends(rate_limit)):
    return _run(payload, "visa")


@router.post("/run-all", response_model=ApiResponse)
def run_all(payload: RunRequest, _: None = Depends(rate_limit)):
    """端到端跑完整条流水线（演示用，会重置此前 Agent 产出）。"""
    payload.auto_advance = True
    payload.reset = True
    return _run(payload, "clue")


@router.get("/trace/{customer_id}", response_model=ApiResponse)
def trace(customer_id: str, limit: int = 100):
    ctx = get_ctx()
    return ApiResponse.ok(ctx.logger.query(customer_id=customer_id, limit=limit))
