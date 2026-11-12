"""容器健康检查（Dockerfile HEALTHCHECK 用，不依赖 curl）。

成功：退出码 0；失败：退出码 1 并打印原因。
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

PORT = os.environ.get("APP_PORT", "8000")
URL = f"http://127.0.0.1:{PORT}/health"


def main() -> int:
    try:
        with urllib.request.urlopen(URL, timeout=4) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"unhealthy: {URL} -> {exc}")
        return 1

    if body.get("status") != "ok":
        print(f"unhealthy: 状态异常 {body}")
        return 1

    rag = body.get("rag") or {}
    total = sum(rag.values())
    if total == 0:
        print("unhealthy: 知识库为空（未执行 ingest_seed.py）")
        return 1

    print(f"healthy: 知识 {total} 条 {rag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
