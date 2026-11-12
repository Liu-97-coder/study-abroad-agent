"""登录与账号接口。

默认账号（首次启动自动创建，可在 .env 里改）：
    admin / admin123        机构负责人：看全部客户
    advisor1 / 123456       顾问：只看自己名下客户
    advisor2 / 123456
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import User, create_token, hash_password, verify_password
from ..schema.common_schema import ApiResponse
from .deps import current_user, get_ctx, require_admin, require_user

router = APIRouter(prefix="/api/auth", tags=["鉴权"])


class LoginRequest(BaseModel):
    username: str
    password: str


class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "advisor"
    display_name: str = ""


@router.post("/login", response_model=ApiResponse)
def login(payload: LoginRequest):
    ctx = get_ctx()
    record = ctx.storage.get_user(payload.username.strip())
    if not record or not verify_password(payload.password, record["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    user = User(record["username"], record["role"], record["display_name"])
    token = create_token(user, ctx.settings.auth_secret, ctx.settings.auth_ttl)
    ctx.logger.event("auth", "login", customer_id="", username=user.username, role=user.role)
    return ApiResponse.ok({
        "token": token,
        "user": user.to_dict(),
        "expires_in": ctx.settings.auth_ttl,
    })


@router.get("/me", response_model=ApiResponse)
def me(user: User = Depends(require_user)):
    return ApiResponse.ok(user.to_dict())


@router.get("/users", response_model=ApiResponse)
def users(_: User = Depends(require_admin)):
    rows = get_ctx().storage.list_users()
    return ApiResponse.ok(rows)


@router.post("/users", response_model=ApiResponse)
def create_user(payload: CreateUserRequest, _: User = Depends(require_admin)):
    if payload.role not in {"admin", "advisor"}:
        raise HTTPException(status_code=400, detail="role 只能是 admin 或 advisor")
    ok = get_ctx().storage.create_user(payload.username, hash_password(payload.password),
                                       payload.role, payload.display_name or payload.username)
    if not ok:
        return ApiResponse.fail("用户名已存在", code=400)
    return ApiResponse.ok({"username": payload.username, "role": payload.role})


@router.get("/whoami", include_in_schema=False)
def whoami():
    user = current_user()
    return {"user": user.to_dict() if user else None}
