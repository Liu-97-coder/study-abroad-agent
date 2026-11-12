"""客户中台 / 系统状态接口。"""
from __future__ import annotations

from fastapi import APIRouter

from ..phase3.risk_agent.handover import build_handover
from ..schema.common_schema import ApiResponse
from ..schema.state_schema import CustomerState
from .deps import assert_can_access, current_user, get_ctx, load_state, visible_owner

router = APIRouter(prefix="/api", tags=["中台"])


@router.get("/customer/list", response_model=ApiResponse)
def customer_list(limit: int = 100):
    rows = get_ctx().storage.list_customers(limit, owner=visible_owner())
    return ApiResponse.ok(rows)


@router.get("/customer/{customer_id}", response_model=ApiResponse)
def customer_detail(customer_id: str):
    data = get_ctx().storage.load_customer(customer_id)
    if not data:
        return ApiResponse.fail("客户不存在", code=404)
    assert_can_access(data)
    return ApiResponse.ok(data)


@router.get("/customer/{customer_id}/tasks", response_model=ApiResponse)
def customer_tasks(customer_id: str, level: str | None = None):
    data = get_ctx().storage.load_customer(customer_id)
    if not data:
        return ApiResponse.fail("客户不存在", code=404)
    assert_can_access(data)
    return ApiResponse.ok(get_ctx().storage.list_tasks(customer_id, level))


@router.get("/customer/{customer_id}/risks", response_model=ApiResponse)
def customer_risks(customer_id: str):
    data = get_ctx().storage.load_customer(customer_id)
    if not data:
        return ApiResponse.fail("客户不存在", code=404)
    assert_can_access(data)
    return ApiResponse.ok(get_ctx().storage.list_risks(customer_id))


@router.get("/customer/{customer_id}/handover", response_model=ApiResponse)
def customer_handover(customer_id: str):
    ctx = get_ctx()
    data = ctx.storage.load_customer(customer_id)
    if not data:
        return ApiResponse.fail("客户不存在", code=404)
    assert_can_access(data)
    result = build_handover(data.get("customer_name", customer_id),
                            [CustomerState(**data)], ctx.storage)
    return ApiResponse.ok(result)


@router.get("/customer/{customer_id}/student-link", response_model=ApiResponse)
def student_link(customer_id: str):
    """生成/返回学生端免登录链接（顾问发给学生用）。"""
    from .student_api import ensure_access_key

    state = load_state(customer_id)
    key = ensure_access_key(state)
    return ApiResponse.ok({"key": key, "url": f"/student.html?k={key}"})


@router.get("/system/me", response_model=ApiResponse)
def whoami():
    return ApiResponse.ok(current_user().to_dict() if current_user() else None)


@router.get("/system/stats", response_model=ApiResponse)
def system_stats():
    ctx = get_ctx()
    user = current_user()
    return ApiResponse.ok({
        "rag": ctx.rag.stats(),
        "storage": ctx.storage.stats(),
        "llm": {**ctx.llm.stats.snapshot(), "provider": ctx.settings.llm_provider,
                "enabled": ctx.llm.available, "cache": ctx.llm.cache.stats()},
        "trace": ctx.logger.stats(),
        "auth": {"enabled": ctx.settings.auth_enabled,
                 "current": user.to_dict() if user else None},
        "config": {
            "rag_backend": ctx.settings.rag_backend,
            "embed_backend": ctx.settings.embed_backend,
            "ocr_backend": ctx.settings.ocr_backend,
            "use_langgraph": ctx.settings.use_langgraph,
        },
    })


@router.get("/system/tasks", response_model=ApiResponse)
def all_tasks(level: str | None = None):
    ctx = get_ctx()
    tasks = ctx.storage.list_tasks(None, level)
    owner = visible_owner()
    if owner:
        allowed = {c["customer_id"] for c in ctx.storage.list_customers(500, owner=owner)}
        tasks = [t for t in tasks if t["customer_id"] in allowed]
    return ApiResponse.ok(tasks)


@router.get("/system/risks", response_model=ApiResponse)
def all_risks():
    ctx = get_ctx()
    risks = ctx.storage.list_risks()
    owner = visible_owner()
    if owner:
        allowed = {c["customer_id"] for c in ctx.storage.list_customers(500, owner=owner)}
        risks = [r for r in risks if r["customer_id"] in allowed]
    return ApiResponse.ok(risks)
