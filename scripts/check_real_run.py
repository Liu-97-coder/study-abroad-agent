"""用真实模型跑一遍完整流程，并报告 token 消耗与耗时。

用法（服务已启动、.env 已配真实 Key）：
    python scripts/check_real_run.py
    python scripts/check_real_run.py --base http://127.0.0.1:8000
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

CHAT = ("学生李同学，南京理工大学计算机专业大三，GPA 3.2/4.0，雅思 6.5，两段实习，"
        "申请英国和香港的计算机硕士，预算 35 万，2027 年 9 月入学。")
PAYLOAD = {
    "customer_questions": "你们能不能保录前 50？",
    "experiences": (
        "1. 2026.07-2026.09 字节跳动 数据分析实习生：用 SQL 清洗 50 万条订单数据，"
        "自动化报表把日报从 3 小时压到 10 分钟。\n"
        "2. 2025.03-2025.12 实验室科研：XGBoost 信用违约预测，12 万样本，AUC 0.76→0.84。"),
    "uploaded_files": [
        {"name": "存款证明",
         "text": "中国银行 存款证明 存款金额 400000 元 存入日期 2026-06-01 存期 180 天"}
    ],
}


def call(base: str, path: str, payload: dict | None = None, token: str | None = None,
         timeout: int = 240):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(base.rstrip("/") + path, data=data,
                                 method="POST" if data else "GET", headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--customer", default="llm-demo")
    args = parser.parse_args()
    base = args.base

    token = call(base, "/api/auth/login",
                 {"username": "admin", "password": "admin123"})["data"]["token"]
    before = call(base, "/api/system/stats", token=token)["data"]["llm"]
    if not before.get("enabled"):
        print("当前是 mock 模式。先跑：python scripts/set_llm_key.py --key sk-xxx")
        return 2
    print(f"模型：{before.get('provider')}\n")

    started = time.time()
    result = call(base, "/api/graph/run-all",
                  {"customer_id": args.customer, "chat_text": CHAT, "payload": PAYLOAD},
                  token=token)["data"]
    elapsed = time.time() - started

    after = call(base, "/api/system/stats", token=token)["data"]["llm"]
    doc = call(base, f"/api/customer/{args.customer}", token=token)["data"]
    outputs = doc.get("agent_outputs") or {}
    ps = ((outputs.get("document") or {}).get("result") or {}).get("ps_content") or ""
    quality = ((outputs.get("document") or {}).get("quality") or {})

    print(f"阶段    : {result.get('stage')}")
    print(f"执行链  : {' → '.join(result.get('history') or [])}")
    print(f"总耗时  : {elapsed:.1f} 秒")
    print(f"LLM 调用: {after['calls'] - before['calls']} 次 "
          f"（缓存命中 {after['cache_hits'] - before['cache_hits']}，"
          f"失败 {after['failures'] - before['failures']}）")
    print(f"token   : {after['prompt_tokens'] - before['prompt_tokens']} 输入 / "
          f"{after['completion_tokens'] - before['completion_tokens']} 输出")
    print(f"PS 字数 : {len(ps)}（英文占比 "
          f"{sum(1 for c in ps if c.isascii()) / max(1, len(ps)):.0%}）")
    print(f"质检    : {quality.get('total')} 分（{quality.get('source')}）")

    if ps:
        print("\n" + "=" * 60)
        print(ps[:600].strip())
        print("=" * 60)
    if result.get("errors"):
        print("异常：", result["errors"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
