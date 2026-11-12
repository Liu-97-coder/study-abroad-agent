"""Offer 解析接口（二期）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..phase2.offer_agent.cas_material_builder import build_plan
from ..phase2.offer_agent.cond_risk_calculator import assess_all
from ..phase2.offer_agent.offer_ocr_parser import parse_offer
from ..phase2.offer_agent.offer_policy_matcher import detect_conflict, match_policy, refund_risk
from ..schema.common_schema import ApiResponse
from ..schema.offer_schema import OfferPolicyInfo
from ..schema.student_schema import StudentBasicInfo
from .deps import get_ctx, load_state, persist, rate_limit

router = APIRouter(prefix="/api/offer", tags=["二期·Offer"])


class OfferRequest(BaseModel):
    customer_id: str
    offer_text: str = ""
    path: str | None = None


def _student(state) -> StudentBasicInfo:
    return StudentBasicInfo(**{k: v for k, v in state.student_info.items()
                               if k in StudentBasicInfo.model_fields})


@router.post("/parse-offer", response_model=ApiResponse)
def parse(payload: OfferRequest, _: None = Depends(rate_limit)):
    ctx = get_ctx()
    state = load_state(payload.customer_id)
    doc = ctx.ocr.parse(path=payload.path, text=payload.offer_text)
    parsed = parse_offer(doc.raw_text, ctx, payload.customer_id)
    conditions, overall = assess_all(parsed["conditions"], _student(state))
    school = parsed["info"].get("school_name", "")
    policy, sources = match_policy(school, parsed["info"].get("major", ""), ctx)
    policy.policy_conflict = detect_conflict(str(parsed["info"].get("deadline", "")), policy)

    state.agent_outputs["offer"] = {
        "school_name": school, "cond_list": [c.model_dump() for c in conditions],
        "policy_info": policy.model_dump(), "overall_risk": overall,
    }
    persist(state)
    return ApiResponse.ok({"info": parsed["info"], "conditions": [c.model_dump() for c in conditions],
                           "policy": policy.model_dump(),
                           "policy_sources": sources, "refund_risk": refund_risk(policy),
                           "overall_risk": overall})


@router.get("/calc-cond-risk", response_model=ApiResponse)
def calc(customer_id: str):
    state = load_state(customer_id)
    offer = state.agent_outputs.get("offer") or {}
    if not offer:
        return ApiResponse.fail("请先调用 /api/offer/parse-offer", code=400)
    from ..schema.offer_schema import CondCondition

    conditions = [CondCondition(**c) for c in offer.get("cond_list", [])]
    assessed, overall = assess_all(conditions, _student(state))
    return ApiResponse.ok({"conditions": [c.model_dump() for c in assessed], "overall_risk": overall})


@router.get("/cas-material-plan", response_model=ApiResponse)
def cas_plan(customer_id: str):
    state = load_state(customer_id)
    offer = state.agent_outputs.get("offer") or {}
    policy = OfferPolicyInfo(**(offer.get("policy_info") or {}))
    plan = build_plan(policy, str(state.student_info.get("arrival_date", "")))
    return ApiResponse.ok(plan)
