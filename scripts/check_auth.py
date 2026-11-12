"""鉴权与数据隔离自检（服务需已启动）。

用法：
    python scripts/check_auth.py --base http://127.0.0.1:8000
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


def call(base: str, path: str, payload: dict | None = None, token: str | None = None):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(base.rstrip("/") + path, data=data,
                                 method="POST" if data else "GET", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            body = {}
        return exc.code, body


def login(base: str, username: str, password: str) -> str | None:
    status, body = call(base, "/api/auth/login", {"username": username, "password": password})
    if status != 200 or body.get("code") != 0:
        print(f"  登录失败 {username}: {status} {body.get('message') or body.get('detail')}")
        return None
    return body["data"]["token"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--admin", default="admin")
    parser.add_argument("--admin-password", default="admin123")
    args = parser.parse_args()
    base = args.base

    results: list[tuple[str, bool, str]] = []

    def check(name, ok, detail=""):
        results.append((name, ok, detail))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}  {detail}")

    print("① 未登录必须被拦截")
    status, _ = call(base, "/api/customer/list")
    check("GET /api/customer/list 无 token → 401", status == 401, f"status={status}")
    status, _ = call(base, "/api/school/match", {"customer_id": "x"})
    check("POST /api/school/match 无 token → 401", status == 401, f"status={status}")
    status, _ = call(base, "/health")
    check("GET /health 公开可访问", status == 200, f"status={status}")

    print("\n② 管理员视角")
    admin = login(base, args.admin, args.admin_password)
    check("admin 登录成功", bool(admin))
    if not admin:
        return 2
    status, body = call(base, "/api/customer/list", token=admin)
    rows = body.get("data") or []
    check("admin 能看到全部客户", status == 200 and len(rows) >= 1, f"{len(rows)} 个")
    print("     " + ", ".join(f"{r['customer_id']}({r.get('owner') or '无归属'})" for r in rows[:6]))

    print("\n③ 顾问视角：只能看自己的")
    advisor = login(base, "advisor1", "123456")
    check("advisor1 登录成功", bool(advisor))
    if not advisor:
        return 2
    status, body = call(base, "/api/customer/list", token=advisor)
    own = body.get("data") or []
    check("advisor1 列表只含自己客户",
          all(r.get("owner") == "advisor1" for r in own) and len(own) >= 1,
          f"{len(own)} 个：{[r['customer_id'] for r in own]}")
    check("advisor1 看不到 admin 的全部",
          len(own) <= len(rows), f"顾问 {len(own)} ≤ 管理员 {len(rows)}")

    others = [r for r in rows if r.get("owner") and r.get("owner") != "advisor1"]
    if others:
        target = others[0]["customer_id"]
        status, _ = call(base, f"/api/customer/{target}", token=advisor)
        check(f"越权访问 {target} → 403", status == 403, f"status={status}")
        status, _ = call(base, f"/api/customer/{target}/tasks", token=advisor)
        check(f"越权读取 {target} 待办 → 403", status == 403, f"status={status}")
    else:
        check("存在他人客户用于越权测试", False, "先跑 scripts/seed_demo.py --reset")

    print("\n④ 伪造/过期 token")
    status, _ = call(base, "/api/customer/list", token="a.b.c")
    check("伪造 token → 401", status == 401, f"status={status}")

    failed = [r for r in results if not r[1]]
    print(f"\n{'全部通过 ✅' if not failed else f'{len(failed)} 项未通过 ❌'}")
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
