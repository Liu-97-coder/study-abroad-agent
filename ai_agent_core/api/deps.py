"""FastAPI 依赖：上下文、当前用户、客户状态装载、限流。

鉴权走中间件写入的 ContextVar，所以各业务接口不用改签名也能拿到当前登录人。
"""
from __future__ import annotations

from contextvars import ContextVar

from fastapi import HTTPException, Request

from ..auth import User
from ..base.context import get_context
from ..schema.state_schema import CustomerState
from ..utils.cache_utils import TokenBucket

_bucket = TokenBucket(capacity=20, per_seconds=60)

_current_user: ContextVar[User | None] = ContextVar("current_user", default=None)


def set_current_user(user: User | None) -> None:
    _current_user.set(user)


def get_ctx():
    return get_context()


def current_user() -> User | None:
    return _current_user.get()


def require_user() -> User:
    user = _current_user.get()
    if user is None:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    return user


def require_admin() -> User:
    user = require_user()
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="需要机构负责人权限")
    return user


def rate_limit(request: Request) -> None:
    """单 IP 每分钟 20 次，防止 Embedding/LLM 被打满。"""
    key = request.client.host if request.client else "anonymous"
    if not _bucket.allow(key):
        raise HTTPException(status_code=429, detail="请求过于频繁，请 1 分钟后再试")


def _can_access(user: User | None, data: dict) -> bool:
    if user is None or user.is_admin:
        return True
    owner = data.get("owner") or ""
    return not owner or owner == user.username


def assert_can_access(data: dict) -> None:
    """给直接用 storage 的接口补上归属校验。"""
    if not _can_access(_current_user.get(), data):
        raise HTTPException(status_code=403, detail="无权访问该客户")


def visible_owner() -> str | None:
    """非管理员返回自己的用户名（用于列表过滤）；管理员返回 None 表示不过滤。"""
    user = _current_user.get()
    if user is None or user.is_admin:
        return None
    return user.username


def load_state(customer_id: str, name: str = "") -> CustomerState:
    ctx = get_ctx()
    data = ctx.storage.load_customer(customer_id)
    user = _current_user.get()
    if data:
        if not _can_access(user, data):
            raise HTTPException(status_code=403, detail="无权访问该客户")
        return CustomerState(**data)
    return CustomerState(customer_id=customer_id,
                         customer_name=name or customer_id,
                         owner=user.username if user else "",
                         trace_id=ctx.logger.new_trace_id())


def apply_chat(state: CustomerState, chat_text: str | None) -> CustomerState:
    if chat_text:
        state.student_info["raw_chat"] = chat_text
    return state


def persist(state: CustomerState) -> CustomerState:
    get_ctx().storage.save_customer(state)
    return state
