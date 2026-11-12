"""接口层自测：启动服务后跑一遍主要接口，确认契约没坏。

用法：
    1) 另开一个终端：uvicorn ai_agent_core.main:app --port 8000
    2) python scripts/api_smoke.py --base http://127.0.0.1:8000
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

CHAT = ("学生王小明，南京理工大学计算机专业大三，GPA 3.2/4.0，均分 82，雅思 6.5，"
        "两段实习，申请英国和香港的计算机硕士，预算 35 万，2027 年 9 月入学。")

_TOKEN: dict[str, str | None] = {"value": None}


def call(base: str, path: str, payload: dict | None = None, method: str | None = None):
    url = base.rstrip("/") + path
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if _TOKEN["value"]:
        headers["Authorization"] = f"Bearer {_TOKEN['value']}"
    req = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"),
                                 headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {"code": exc.code, "message": exc.read().decode("utf-8", "ignore"), "data": None}


def login(base: str, username: str = "admin", password: str = "admin123") -> bool:
    result = call(base, "/api/auth/login", {"username": username, "password": password})
    data = result.get("data") or {}
    _TOKEN["value"] = data.get("token")
    user = data.get("user") or {}
    print(f"/api/auth/login → {user.get('username')} / {user.get('role')} "
          f"token={'有' if _TOKEN['value'] else '无'}")
    return bool(_TOKEN["value"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base = args.base

    health = call(base, "/health")
    print(f"/health → {health.get('status')} | RAG {health.get('rag')}")

    if not login(base):
        print("登录失败：确认服务已启动且已初始化默认账号")
        return 2

    r = call(base, "/api/auth/me")
    print(f"/api/auth/me → {(r.get('data') or {}).get('username')}")

    r = call(base, "/api/system/stats")
    print(f"/api/system/stats → 鉴权 {(r.get('data') or {}).get('auth', {}).get('enabled')}")

    r = call(base, "/api/school/extract", {"customer_id": "api-001", "chat_text": CHAT, "name": "王小明"})
    student = (r.get("data") or {}).get("student", {})
    print(f"/api/school/extract → GPA {student.get('gpa')} 雅思 {student.get('ielts')} "
          f"国家 {student.get('target_country')} 缺失 {len((r.get('data') or {}).get('missing_info', []))} 项")

    r = call(base, "/api/school/match", {"customer_id": "api-001", "chat_text": CHAT})
    counts = (r.get("data") or {}).get("counts", {})
    print(f"/api/school/match → {counts}")

    r = call(base, "/api/school/report", {"customer_id": "api-001"})
    md = ((r.get("data") or {}).get("markdown") or "")
    print(f"/api/school/report → {len(md)} 字，首行 {md.splitlines()[0] if md else '(空)'}")

    r = call(base, "/api/school/talk", {"customer_id": "api-001", "question": "能不能保录前 50？"})
    d = r.get("data") or {}
    print(f"/api/school/talk → 意图 {d.get('intent')} 风险 {d.get('safety_level')} "
          f"拦截 {d.get('safety_blocked')}")

    r = call(base, "/api/school/summary", {"customer_id": "api-001", "chat_text": CHAT})
    print(f"/api/school/summary → {(r.get('data') or {}).get('source')} 模式，"
          f"{(len((r.get('data') or {}).get('markdown') or ''))} 字")

    r = call(base, "/api/doc/parse-experience",
             {"customer_id": "api-001", "experiences": "2026.07-2026.09 字节跳动 数据分析实习生："
                                                        "清洗 50 万条数据，报表 3 小时缩短到 10 分钟。"})
    print(f"/api/doc/parse-experience → {(r.get('data') or {}).get('count')} 条经历")

    r = call(base, "/api/doc/generate-ps", {"customer_id": "api-001", "experiences": ""})
    print(f"/api/doc/generate-ps → {len((r.get('data') or {}).get('content') or '')} 字")

    r = call(base, "/api/material/build-list", {"customer_id": "api-001"})
    print(f"/api/material/build-list → {(len((r.get('data') or {}).get('material_list') or []))} 项")

    r = call(base, "/api/visa/get-visa-timeline?customer_id=api-001&arrival_date=2027-09-01")
    print(f"/api/visa/get-visa-timeline → 风险 {(r.get('data') or {}).get('risk')}，"
          f"{(len((r.get('data') or {}).get('nodes') or []))} 个节点")

    r = call(base, "/api/graph/run-all", {"customer_id": "api-001", "chat_text": CHAT})
    d = r.get("data") or {}
    print(f"/api/graph/run-all → 阶段 {d.get('stage')} 引擎 {d.get('engine')} "
          f"执行 {len(d.get('history') or [])} 个 Agent 新增待办 {len(d.get('new_tasks') or [])} 条")

    r = call(base, "/api/customer/api-001")
    print(f"/api/customer/api-001 → 阶段 {(r.get('data') or {}).get('stage')}")

    r = call(base, "/api/system/stats")
    d = r.get("data") or {}
    print(f"/api/system/stats → LLM {d.get('llm', {}).get('provider')} "
          f"知识库 {d.get('rag')} 中台 {d.get('storage')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
