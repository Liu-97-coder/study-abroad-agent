"""FastAPI 入口（同时托管 Web 控制台）。

启动：
    powershell -ExecutionPolicy Bypass -File scripts\\dev.ps1
访问：
    http://127.0.0.1:8000/          控制台
    http://127.0.0.1:8000/docs     接口文档
"""
from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

if sys.platform == "win32":  # Windows 控制台中文输出
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import (application_api, auth_api, customer_api, dashboard_api, document_api,
                  graph_trigger_api, interview_api, material_api, offer_api,
                  school_api, student_api, visa_api)
from .api.deps import set_current_user
from .auth import User, bearer_token, decode_token
from .base.context import get_context
from .config import COLLECTIONS, PROJECT_DIR, settings

WEB_DIR = PROJECT_DIR / "web"
INDEX_FILE = WEB_DIR / "index.html"

# 无需登录即可访问的路径（登录页、健康检查、静态资源、接口文档）
PUBLIC_PATHS = {"/", "/health", "/api/auth/login", "/api/dashboard/health", "/student", "/student.html"}
PUBLIC_PREFIXES = ("/static", "/docs", "/redoc", "/openapi.json", "/favicon.ico", "/api/student")


@asynccontextmanager
async def lifespan(app: FastAPI):
    ctx = get_context()
    stats = ctx.rag.stats()
    if sum(stats.values()) == 0:
        print("[warn] 知识库为空，请先运行：python scripts/ingest_seed.py")

    created = ctx.storage.ensure_default_users(
        settings.auth_default_admin, settings.auth_default_password,
        extras=[("advisor1", "123456", "advisor", "顾问·李"),
                ("advisor2", "123456", "advisor", "顾问·王")])
    if created:
        print(f"[ok] 初始化 {created} 个账号：admin/admin123、advisor1/123456、advisor2/123456")

    print(f"[ok] LLM={settings.llm_provider} RAG={settings.rag_backend} "
          f"embed={settings.embed_backend} OCR={settings.ocr_backend} "
          f"鉴权={'开启' if settings.auth_enabled else '关闭'}")
    print(f"[ok] Web 控制台：http://127.0.0.1:<端口>/   接口文档：/docs")
    yield


app = FastAPI(
    title="留学全流程智能顾问 Agent 系统",
    description="RAG + 多 Agent 调度 + 风控护栏（对应语雀《项目经验扩展库》全套设计）",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

for module in (school_api, document_api, material_api, application_api,
               offer_api, visa_api, graph_trigger_api, customer_api, dashboard_api,
               auth_api, student_api, interview_api):
    app.include_router(module.router)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """统一鉴权：白名单外的请求必须带有效 Bearer Token。"""
    ctx = get_context()
    path = request.url.path

    if not ctx.settings.auth_enabled:
        set_current_user(User("local", "admin", "本地模式（未开鉴权）"))
        return await call_next(request)

    if path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES):
        return await call_next(request)

    token = bearer_token(request.headers.get("authorization"))
    user = decode_token(token, ctx.settings.auth_secret) if token else None
    if user is None:
        return JSONResponse(status_code=401,
                            content={"code": 401, "message": "未登录或登录已过期", "data": None})

    set_current_user(user)
    return await call_next(request)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"code": 500, "message": str(exc), "data": None})


@app.get("/health", tags=["系统"])
def health():
    ctx = get_context()
    return {"status": "ok", "version": "1.1.0",
            "collections": list(COLLECTIONS), "rag": ctx.rag.stats()}


# ---------- Web 控制台（零构建：纯 HTML/CSS/JS） ----------
if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@app.get("/", include_in_schema=False)
def index():
    if INDEX_FILE.exists():
        return FileResponse(str(INDEX_FILE))
    return JSONResponse({
        "name": "留学全流程智能顾问 Agent 系统",
        "docs": "/docs",
        "health": "/health",
        "tips": "web/index.html 不存在；先跑 python scripts/ingest_seed.py 再访问 /docs",
    })


@app.get("/student", include_in_schema=False)
@app.get("/student.html", include_in_schema=False)
def student_page():
    page = WEB_DIR / "student.html"
    if page.exists():
        return FileResponse(str(page))
    return JSONResponse(status_code=404, content={"message": "student.html 不存在"})


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    icon = WEB_DIR / "favicon.svg"
    if icon.exists():
        return FileResponse(str(icon), media_type="image/svg+xml")
    return JSONResponse(status_code=204, content=None)
