"""文书模块接口（一期）。

POST /api/doc/parse-experience  经历结构化解析
POST /api/doc/generate-cv       生成 CV
POST /api/doc/generate-ps       生成 PS
POST /api/doc/generate-ref      生成推荐信
POST /api/doc/quality-check     文书质检
POST /api/doc/version-save      版本保存
GET  /api/doc/versions          版本列表
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..phase1.doc_agent.cv_generator import generate_cv
from ..phase1.doc_agent.doc_quality_check import check_document
from ..phase1.doc_agent.doc_version_mgr import DocVersionManager
from ..phase1.doc_agent.experience_parse import build_experience_text, parse_experiences
from ..phase1.doc_agent.ps_generator import generate_ps
from ..phase1.doc_agent.ref_generator import generate_refs
from ..schema.common_schema import ApiResponse
from ..schema.student_schema import StudentBasicInfo
from .deps import get_ctx, load_state, persist, rate_limit

router = APIRouter(prefix="/api/doc", tags=["一期·文书"])


class DocRequest(BaseModel):
    customer_id: str
    experiences: str | list = ""
    target_major: str = ""


class QualityRequest(BaseModel):
    customer_id: str
    doc_text: str


class VersionRequest(BaseModel):
    customer_id: str
    doc_type: str
    content: str
    status: str = "待修改"


def _student(state) -> StudentBasicInfo:
    return StudentBasicInfo(**{k: v for k, v in state.student_info.items()
                               if k in StudentBasicInfo.model_fields})


@router.post("/parse-experience", response_model=ApiResponse)
def parse_experience(payload: DocRequest, _: None = Depends(rate_limit)):
    experiences = parse_experiences(payload.experiences)
    return ApiResponse.ok({
        "count": len(experiences),
        "experiences": [e.model_dump() for e in experiences],
        "prompt_text": build_experience_text(experiences),
    })


@router.post("/generate-cv", response_model=ApiResponse)
def gen_cv(payload: DocRequest, _: None = Depends(rate_limit)):
    ctx = get_ctx()
    state = load_state(payload.customer_id)
    student = _student(state)
    experiences = parse_experiences(payload.experiences or state.student_info.get("experiences", ""))
    data = generate_cv(student, experiences, ctx, payload.customer_id)
    return ApiResponse.ok(data)


@router.post("/generate-ps", response_model=ApiResponse)
def gen_ps(payload: DocRequest, _: None = Depends(rate_limit)):
    ctx = get_ctx()
    state = load_state(payload.customer_id)
    student = _student(state)
    experiences = parse_experiences(payload.experiences or state.student_info.get("experiences", ""))
    data = generate_ps(student, experiences, ctx, payload.customer_id)
    return ApiResponse.ok(data)


@router.post("/generate-ref", response_model=ApiResponse)
def gen_ref(payload: DocRequest, _: None = Depends(rate_limit)):
    ctx = get_ctx()
    state = load_state(payload.customer_id)
    student = _student(state)
    experiences = parse_experiences(payload.experiences or state.student_info.get("experiences", ""))
    return ApiResponse.ok(generate_refs(student, experiences, ctx, payload.customer_id))


@router.post("/quality-check", response_model=ApiResponse)
def quality_check(payload: QualityRequest, _: None = Depends(rate_limit)):
    ctx = get_ctx()
    state = load_state(payload.customer_id)
    student = _student(state)
    experiences = parse_experiences(state.student_info.get("experiences", ""))
    context = "\n".join(c.content for c in ctx.rag.search(
        "writing", f"{student.target_major or ''} 课程", top_k=6, rerank_top=3))
    result = check_document(payload.doc_text, student, experiences, context,
                            ctx, payload.customer_id)
    return ApiResponse.ok(result)


@router.post("/version-save", response_model=ApiResponse)
def version_save(payload: VersionRequest, _: None = Depends(rate_limit)):
    mgr = DocVersionManager(get_ctx().storage, get_ctx().logger)
    version_id = mgr.save(payload.customer_id, payload.doc_type, payload.content, payload.status)
    return ApiResponse.ok({"version_id": version_id})


@router.get("/versions", response_model=ApiResponse)
def versions(customer_id: str, doc_type: str | None = None):
    return ApiResponse.ok(get_ctx().storage.list_versions(customer_id, doc_type))
