"""长期运行入口：被计划任务调用，输出重定向到 logs/server.log，崩溃自动重启。

为什么不用 uvicorn --reload：生产不要热重载（改了代码会在半夜重启服务）。
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG = LOG_DIR / "server.log"
PORT = os.environ.get("APP_PORT", "8000")
PY = ROOT / ".venv" / "Scripts" / "python.exe"
if not PY.exists():
    PY = Path(sys.executable)

MAX_RESTARTS = 20


def main() -> int:
    started = time.time()
    restarts = 0
    while restarts <= MAX_RESTARTS:
        with LOG.open("a", encoding="utf-8") as fp:
            fp.write(f"\n=== start {time.strftime('%Y-%m-%d %H:%M:%S')} "
                     f"(restart #{restarts}) ===\n")
            fp.flush()
            proc = subprocess.Popen(
                [str(PY), "-m", "uvicorn", "ai_agent_core.main:app",
                 "--host", "0.0.0.0", "--port", PORT, "--log-level", "info"],
                cwd=str(ROOT), stdout=fp, stderr=subprocess.STDOUT,
            )
            code = proc.wait()

        restarts += 1
        with LOG.open("a", encoding="utf-8") as fp:
            fp.write(f"=== exit code {code}, uptime {time.time() - started:.0f}s ===\n")
        if restarts > MAX_RESTARTS:
            with LOG.open("a", encoding="utf-8") as fp:
                fp.write("=== too many restarts, giving up ===\n")
            return 1
        time.sleep(min(30, 3 * restarts))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
