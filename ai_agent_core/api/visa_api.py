"""签证接口（二期）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..phase2.visa_agent.fund_risk_analyzer import analyze_fund
from ..phase2.visa_agent.visa_material_builder import build_visa_materials
from ..phase2.visa_agent.visa_timeline_planner import plan_timeline
from ..schema.common_schema import ApiResponse
from ..schema.student_schema import StudentBasicInfo
from .deps import get_ctx, load_state, rate_limit

router = APIRouter(prefix="/api/visa", tags=["二期·签证"])


class VisaListRequest(BaseModel):
    customer_id: str
    country: str = ""
    fund_from_parent: bool = True


class FundRequest(BaseModel):
    customer_id: str
    fund_data: dict


def _student(state) -> StudentBasicInfo:
    return StudentBasicInfo(**{k: v for k, v in state.student_info.items()
                               if k in StudentBasicInfo.model_fields})


@router.post("/build-visa-list", response_model=ApiResponse)
def build_list(payload: VisaListRequest, _: None = Depends(rate_limit)):
    state = load_state(payload.customer_id)
    country = payload.country or (_student(state).target_country or ["英国"])[0]
    items = build_visa_materials(_student(state), country, payload.fund_from_parent)
    return ApiResponse.ok({"country": country,
                           "materials": [i.model_dump() for i in items]})


@router.post("/analyze-fund", response_model=ApiResponse)
def analyze(payload: FundRequest, _: None = Depends(rate_limit)):
    ctx = get_ctx()
    state = load_state(payload.customer_id)
    country = (_student(state).target_country or ["英国"])[0]
    risks, amount, level = analyze_fund(payload.fund_data, country, ctx, payload.customer_id)
    return ApiResponse.ok({"country": country, "fund_total": amount, "overall": level,
                           "risks": [r.model_dump() for r in risks]})


@router.get("/get-visa-timeline", response_model=ApiResponse)
def timeline(customer_id: str, arrival_date: str = "", cas_date: str = ""):
    state = load_state(customer_id)
    country = (_student(state).target_country or ["英国"])[0]
    arrival = arrival_date or str(state.student_info.get("arrival_date", ""))
    cas = cas_date or str(state.student_info.get("cas_date", ""))
    data = plan_timeline(arrival, cas, country)
    return ApiResponse.ok({**data, "nodes": [n.model_dump() for n in data["nodes"]]})
