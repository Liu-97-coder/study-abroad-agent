"""管理看板接口（给 Web 控制台的「风控看板」页用）。

数据全部来自客户中台（SQLite），不额外维护统计表 —— 口径永远与业务一致。
"""
from __future__ import annotations

from collections import Counter

from fastapi import APIRouter

from ..config import STAGES, STAGE_LABELS
from ..schema.common_schema import ApiResponse
from .deps import current_user, get_ctx, visible_owner

router = APIRouter(prefix="/api/dashboard", tags=["看板"])


@router.get("/overview", response_model=ApiResponse)
def overview():
    ctx = get_ctx()
    store = ctx.storage
    owner = visible_owner()

    customers = store.list_customers(limit=500, owner=owner)
    allowed = None if owner is None else {c["customer_id"] for c in customers}

    stage_counter = Counter(c["stage"] for c in customers)
    by_stage = [
        {"stage": s, "label": STAGE_LABELS.get(s, s), "count": stage_counter.get(s, 0)}
        for s in STAGES
    ]

    tasks = store.list_tasks()
    if allowed is not None:
        tasks = [t for t in tasks if t["customer_id"] in allowed]
    level_counter = Counter(t["level"] for t in tasks)
    urgent = [t for t in tasks if t["level"] == "紧急"][:8]

    risks = store.list_risks()
    if allowed is not None:
        risks = [r for r in risks if r["customer_id"] in allowed]
    tag_counter = Counter(r["tag"] for r in risks)
    risk_level = Counter(r["level"] for r in risks)

    # 文书产出：按客户统计版本数
    versions = 0
    for c in customers:
        versions += len(store.list_versions(c["customer_id"]))

    signed = sum(1 for c in customers if c["stage"] not in {"clue", "consult"})
    finished = stage_counter.get("finished", 0)
    conversion = round(signed / len(customers) * 100, 1) if customers else 0.0

    # 流程完成度：按"客户是否已产出该 Agent 的结果"统计，比只看当前阶段更有信息量
    datas = store.list_customer_data(limit=500)
    if allowed is not None:
        datas = [d for d in datas if d.get("customer_id") in allowed]
    steps = [("school", "选校"), ("material", "材料"), ("document", "文书"),
             ("application", "网申"), ("offer", "Offer"), ("visa", "签证"), ("risk", "风控")]
    pipeline = [{
        "key": key, "label": label,
        "count": sum(1 for d in datas if (d.get("agent_outputs") or {}).get(key)),
    } for key, label in steps]

    return ApiResponse.ok({
        "customers": {"total": len(customers), "by_stage": by_stage,
                      "signed": signed, "conversion": conversion},
        "pipeline": pipeline,
        "tasks": {"total": len(tasks), "by_level": dict(level_counter), "urgent": urgent},
        "risks": {"total": len(risks), "by_level": dict(risk_level),
                  "top": [{"tag": t, "count": n} for t, n in tag_counter.most_common(8)]},
        "documents": {"versions": versions},
        "finished": finished,
        "recent": customers[:8],
    })


@router.get("/health", response_model=ApiResponse)
def health():
    """给前端登录页/顶栏状态灯用（公开接口，不含敏感数据）。"""
    ctx = get_ctx()
    rag = ctx.rag.stats()
    user = current_user()
    return ApiResponse.ok({
        "status": "ok",
        "knowledge": sum(rag.values()),
        "collections": rag,
        "llm": ctx.settings.llm_provider,
        "llm_live": ctx.llm.available,
        "customers": ctx.storage.stats().get("customers", 0),
        "auth_enabled": ctx.settings.auth_enabled,
        "user": user.to_dict() if user else None,
    })
