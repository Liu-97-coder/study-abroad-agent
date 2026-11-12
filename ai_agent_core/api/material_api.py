"""材料模块接口（二期）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..phase2.material_agent.material_list_builder import build_custom_material_list
from ..phase2.material_agent.material_notice_generator import generate_notice
from ..phase2.material_agent.material_rule_checker import check_material
from ..phase2.material_agent.material_task_generator import build_todo, missing_diff
from ..schema.common_schema import ApiResponse
from ..schema.student_schema import StudentBasicInfo
from .deps import get_ctx, load_state, persist, rate_limit

router = APIRouter(prefix="/api/material", tags=["二期·材料"])


class ListRequest(BaseModel):
    customer_id: str
    submit_deadline: str = ""
    language_course: bool = False
    fund_from_parent: bool = True


class CheckRequest(BaseModel):
    customer_id: str
    material_name: str
    text: str = ""
    path: str | None = None


def _student(state) -> StudentBasicInfo:
    return StudentBasicInfo(**{k: v for k, v in state.student_info.items()
                               if k in StudentBasicInfo.model_fields})


@router.post("/build-list", response_model=ApiResponse)
def build_list(payload: ListRequest, _: None = Depends(rate_limit)):
    ctx = get_ctx()
    state = load_state(payload.customer_id)
    items, meta = build_custom_material_list(_student(state), ctx, payload.submit_deadline,
                                             payload.language_course, payload.fund_from_parent)
    return ApiResponse.ok({"material_list": [i.model_dump() for i in items], "policy": meta})


@router.post("/check-file", response_model=ApiResponse)
def check_file(payload: CheckRequest, _: None = Depends(rate_limit)):
    ctx = get_ctx()
    state = load_state(payload.customer_id)
    doc = ctx.ocr.parse(path=payload.path, text=payload.text)
    result = check_material(payload.material_name, doc, _student(state),
                            (_student(state).target_country or ["英国"])[0])
    return ApiResponse.ok({"result": result.model_dump(),
                           "ocr": {"file_type": doc.file_type, "confidence": doc.confidence,
                                   "errors": doc.errors, "warnings": doc.warnings}})


@router.post("/get-risk-todo", response_model=ApiResponse)
def get_risk_todo(payload: ListRequest, _: None = Depends(rate_limit)):
    ctx = get_ctx()
    state = load_state(payload.customer_id)
    items, _ = build_custom_material_list(_student(state), ctx, payload.submit_deadline)
    uploaded = [u.get("name", "") for u in state.student_info.get("uploaded_files") or []]
    missing = missing_diff(items, uploaded)
    todo = build_todo(missing, None)
    notice = generate_notice([m.material_name for m in missing], 0)
    for task in todo:
        state.add_task(task["title"], level=task["level"], due_date=task["due_date"],
                       source="material_agent")
    persist(state)
    return ApiResponse.ok({"missing": [m.material_name for m in missing],
                           "todo": todo, "notice": notice})
