"""部署等价验证：用干净虚拟环境 + 只装 requirements.txt，证明镜像依赖完整。

Docker 镜像 = python:slim + pip install -r requirements.txt + 拷代码。
所以"干净 venv 能跑起来"≈"镜像构建后能跑起来"（差别只在系统库，本项目不需要编译型系统库）。

用法：
    python scripts/check_deploy.py              # 建临时 venv 验证（约 1-2 分钟）
    python scripts/check_deploy.py --keep       # 保留 venv 便于排查
    python scripts/check_deploy.py --mirror https://pypi.tuna.tsinghua.edu.cn/simple
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PROBE = r'''
import json, sys
from fastapi.testclient import TestClient
from ai_agent_core.main import app

failures = []
def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}  {detail}")
    if not ok:
        failures.append(name)

with TestClient(app) as client:
    health = client.get("/health")
    check("GET /health", health.status_code == 200, f"status={health.status_code}")
    rag = (health.json() or {}).get("rag", {})
    check("知识库已加载", sum(rag.values()) > 0, str(rag))

    index = client.get("/")
    check("控制台首页", index.status_code == 200 and "留学 Agent 控制台" in index.text)

    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    token = (login.json().get("data") or {}).get("token")
    check("默认账号可登录", bool(token), f"status={login.status_code}")

    headers = {"Authorization": f"Bearer {token}"} if token else {}
    match = client.post("/api/school/match",
                        json={"customer_id": "deploy-check",
                              "chat_text": "学生测试，南京理工大学计算机专业，GPA 3.2，雅思 6.5，申请英国计算机硕士。"},
                        headers=headers)
    data = (match.json() or {}).get("data") or {}
    counts = data.get("counts") or {}
    check("选校链路可用", sum(counts.values()) > 0, str(counts))

    dash = client.get("/api/dashboard/overview", headers=headers)
    check("看板接口", dash.status_code == 200 and "pipeline" in (dash.json().get("data") or {}))

print(json.dumps({"failures": failures}, ensure_ascii=False))
sys.exit(1 if failures else 0)
'''


def run(cmd: list[str], cwd: Path | None = None, timeout: int = 1800,
        extra_env: dict | None = None) -> subprocess.CompletedProcess:
    env = None
    if extra_env:
        import os

        env = {**os.environ, **extra_env}
    return subprocess.run(cmd, cwd=str(cwd or ROOT), capture_output=True, text=True,
                          timeout=timeout, encoding="utf-8", errors="ignore", env=env)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--mirror", default="")
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()

    venv_dir = Path(tempfile.mkdtemp(prefix="deploy-venv-"))
    probe = venv_dir / "probe.py"
    probe.write_text(PROBE, encoding="utf-8")

    print(f"① 建干净虚拟环境：{venv_dir}")
    started = time.time()
    result = run([args.python, "-m", "venv", str(venv_dir)])
    if result.returncode != 0:
        print("建 venv 失败：", result.stderr[-500:])
        return 2
    py = venv_dir / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    print(f"   解释器：{py}")

    print("\n② 只装 requirements.txt（模拟 Dockerfile 的 pip 层）")
    pip_args = [str(py), "-m", "pip", "install", "--quiet", "-r", "requirements.txt"]
    if args.mirror:
        pip_args += ["-i", args.mirror]
    result = run(pip_args, timeout=3600)
    if result.returncode != 0:
        print("依赖安装失败：")
        print((result.stdout + result.stderr)[-1500:])
        return 2
    print(f"   [ok] 安装完成，用时 {time.time() - started:.0f}s")

    print("\n③ 用干净环境跑应用（导入 → 健康检查 → 登录 → 选校 → 看板）")
    # 直接把项目根塞进 PYTHONPATH：等价于容器里 WORKDIR /app 的效果
    env_run = run([str(py), str(probe)], cwd=ROOT, timeout=600,
                  extra_env={"PYTHONPATH": str(ROOT), "AUTH_ENABLED": "1"})
    print(env_run.stdout.rstrip() or env_run.stderr[-800:])
    ok = env_run.returncode == 0

    if not args.keep:
        shutil.rmtree(venv_dir, ignore_errors=True)
    else:
        print(f"\n保留环境：{venv_dir}")

    print(f"\n总耗时 {time.time() - started:.0f}s")
    print("全部通过 ✅ —— requirements.txt 已覆盖运行所需依赖，镜像可构建"
          if ok else "有失败项 ❌ —— 说明 requirements.txt 缺依赖或代码有新依赖未声明")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
