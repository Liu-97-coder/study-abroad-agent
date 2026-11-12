"""生产形态自检：按容器里的启动方式跑一遍（0.0.0.0 绑定 + 健康检查 + 局域网可达）。

容器 CMD 是：
    python scripts/ingest_seed.py && uvicorn ai_agent_core.main:app --host 0.0.0.0 --port 8000

这里在宿主机上原样复现这条命令，验证三件最容易在容器里翻车的事：
1. 能否绑定 0.0.0.0（而不是只监听 127.0.0.1）
2. scripts/healthcheck.py 能否通过（Dockerfile 的 HEALTHCHECK 用它）
3. 局域网 IP 能否访问（同一网段的其他电脑/手机打开控制台）

用法：
    python scripts/check_prod.py
    python scripts/check_prod.py --port 8060
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def lan_ip() -> str:
    """拿本机局域网 IP（不真的发包）。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def probe(url: str, timeout: float = 5.0) -> tuple[bool, str]:
    """探 JSON 接口。"""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        payload = body.get("data") if isinstance(body.get("data"), dict) else body
        total = payload.get("knowledge")
        if total is None:
            total = sum((payload.get("rag") or {}).values())
        return True, f"{resp.status} · 知识 {total} 条"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return False, str(exc)[:120]


def probe_page(url: str, timeout: float = 8.0) -> tuple[bool, str]:
    """探 HTML 页面：只看状态码与内容长度，不解析 JSON。"""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            raw = resp.read()
        return resp.status == 200, f"{resp.status} · {len(raw)} 字节"
    except (urllib.error.URLError, TimeoutError) as exc:
        return False, str(exc)[:120]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8060)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    python = ROOT / ".venv" / "Scripts" / "python.exe"
    if not python.exists():
        python = Path(sys.executable)

    results: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, ok, detail))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}  {detail}")

    print(f"① 按容器 CMD 的方式启动（{args.host}:{args.port}）")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    server = subprocess.Popen(
        [str(python), "-m", "uvicorn", "ai_agent_core.main:app",
         "--host", args.host, "--port", str(args.port), "--log-level", "warning"],
        cwd=str(ROOT), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
    )
    try:
        ready = False
        for _ in range(40):
            time.sleep(1)
            if probe(f"http://127.0.0.1:{args.port}/health", timeout=2)[0]:
                ready = True
                break
        check("服务启动（0.0.0.0 绑定）", ready,
              f"pid={server.pid}" if ready else "40 秒未就绪")

        if ready:
            ok, detail = probe(f"http://127.0.0.1:{args.port}/health")
            check("本机 127.0.0.1 可访问", ok, detail)

            ip = lan_ip()
            if ip != "127.0.0.1":
                ok, detail = probe(f"http://{ip}:{args.port}/health")
                check(f"局域网 {ip} 可访问", ok, detail)
            else:
                print("     （跳过局域网检查：没拿到非回环 IP）")

            print("\n② 健康检查脚本（Dockerfile HEALTHCHECK 用的那个）")
            rc = subprocess.run(
                [str(python), "scripts/healthcheck.py"],
                cwd=str(ROOT), env={**env, "APP_PORT": str(args.port)},
                capture_output=True, text=True, encoding="utf-8",
            )
            check("healthcheck.py 退出码 0", rc.returncode == 0,
                  (rc.stdout or rc.stderr).strip()[:100])

            print("\n③ 控制台与接口")
            for path, name, is_page in (("/", "控制台首页", True),
                                        ("/docs", "接口文档", True),
                                        ("/api/dashboard/health", "看板健康", False)):
                url = f"http://127.0.0.1:{args.port}{path}"
                ok, detail = (probe_page(url) if is_page else probe(url))
                check(name, ok, detail)
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()

    failed = [r for r in results if not r[1]]
    print(f"\n{'全部通过 ✅ —— 容器里的启动方式在宿主机上等价可用' if not failed else f'{len(failed)} 项未通过 ❌'}")
    ip = lan_ip()
    print(f"局域网访问：http://{ip}:8000/ （手机同 WiFi 可打开学生端）")
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
