"""RAG 检索诊断：看看你的知识库到底召回了什么。

用法：
    python scripts/check_rag.py --collection school --query "英国 计算机硕士" --country 英国
    python scripts/check_rag.py --collection visa --query "存款 存期 28 天"
    python scripts/check_rag.py --stats
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

from ai_agent_core.base.context import get_context  # noqa: E402
from ai_agent_core.config import COLLECTIONS  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--collection", default="school", choices=list(COLLECTIONS))
    parser.add_argument("--query", default="")
    parser.add_argument("--country", default="")
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--stats", action="store_true")
    args = parser.parse_args()

    ctx = get_context()
    if args.stats or not args.query:
        print("各库条数：", ctx.rag.stats())
        return 0

    where = {"country": {"$in": [args.country]}} if args.country else None
    chunks = ctx.rag.search(args.collection, args.query, where=where,
                            top_k=max(args.top * 3, 10), rerank_top=args.top)
    print(f"查询：{args.query!r} | 库：{args.collection} | 过滤：{where}")
    if not chunks:
        print("（无命中，检查是否已跑 scripts/ingest_seed.py）")
        return 1
    for idx, chunk in enumerate(chunks, 1):
        print(f"\n[{idx}] score={chunk.score}  source={chunk.source_info.get('source_id')}")
        print(f"    {chunk.source_info.get('source_name')} | "
              f"元数据字段：{list(chunk.metadata.keys())[:8]}")
        print("    " + chunk.content.replace("\n", " ")[:180])
    print("\n喂给 LLM 的上下文预览：")
    print(ctx.rag.format_context(chunks, max_chars=600))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
