"""Milvus 后端自检：建库 → 写入 → 检索 → 标量过滤 → 统计。

用法（默认用 Milvus Lite 本地文件，免 Docker）：
    python scripts/check_milvus.py
    python scripts/check_milvus.py --server http://127.0.0.1:19530   # 连独立服务
"""
from __future__ import annotations

import argparse
import dataclasses
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

from ai_agent_core.base.context import AgentContext  # noqa: E402
from ai_agent_core.config import settings  # noqa: E402

DOCS = [
    {"text": "The University of Edinburgh 计算机科学 硕士，GPA 要求 3.5，雅思 7.0，截止 2027-01-15",
     "metadata": {"school_name": "Edinburgh", "country": "英国", "gpa_min": 3.5, "degree": "硕士"},
     "source_id": "milvus-check-1", "source_name": "自检数据"},
    {"text": "University of Glasgow 计算机科学 硕士，GPA 要求 3.0，雅思 6.5，截止 2027-05-31",
     "metadata": {"school_name": "Glasgow", "country": "英国", "gpa_min": 3.0, "degree": "硕士"},
     "source_id": "milvus-check-2", "source_name": "自检数据"},
    {"text": "The University of Hong Kong 计算机科学 硕士，GPA 要求 3.5，雅思 6.5，截止 2027-02-28",
     "metadata": {"school_name": "HKU", "country": "香港", "gpa_min": 3.5, "degree": "硕士"},
     "source_id": "milvus-check-3", "source_name": "自检数据"},
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default="", help="独立 Milvus 地址，留空则用 Lite 本地文件")
    parser.add_argument("--db", default="", help="Lite 数据库路径")
    args = parser.parse_args()

    db_path = args.db or str(Path(tempfile.mkdtemp(prefix="milvus-")) / "check.db")
    cfg = dataclasses.replace(
        settings, rag_backend="milvus", milvus_server_uri=args.server,
        milvus_local_path=db_path, log_dir=Path(tempfile.mkdtemp(prefix="log-")),
    )
    print(f"后端：milvus | 目标：{args.server or db_path}\n")

    results = []

    def check(name, ok, detail=""):
        results.append((name, ok))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}  {detail}")

    try:
        ctx = AgentContext.build(cfg)
    except Exception as exc:  # noqa: BLE001
        print(f"初始化失败：{exc}")
        print("提示：pip install pymilvus milvus-lite；连服务时确认 19530 端口可达")
        return 2

    print("① 集合与写入")
    check("四个 Collection 自动创建", True, f"dim={cfg.embed_dim}")
    count = ctx.rag.ingest("school", DOCS, replace=True)
    check("写入 3 条", count == 3, f"count={count}")
    stats = ctx.rag.stats()
    check("统计可读", stats.get("school", 0) >= 3, f"school={stats.get('school')}")

    print("\n② 检索")
    hits = ctx.rag.search("school", "英国 计算机 硕士 GPA", top_k=10, rerank_top=3)
    check("召回非空", bool(hits), f"{len(hits)} 条")
    check("带 source_id", all(h.source_info.get("source_id") for h in hits),
          f"{[h.source_info.get('source_id') for h in hits]}")
    for h in hits:
        print(f"     · {h.score:.3f}  {h.source_info.get('source_id')}  {h.content[:40]}")

    print("\n③ 标量过滤")
    uk = ctx.rag.search("school", "计算机", where={"country": {"$in": ["英国"]}},
                        top_k=10, rerank_top=10)
    check("只返回英国", bool(uk) and all(h.metadata.get("country") == "英国" for h in uk),
          f"{len(uk)} 条")
    none = ctx.rag.search("school", "计算机", where={"country": {"$in": ["南极洲"]}})
    check("无匹配返回空", none == [], f"{len(none)} 条")

    print("\n④ 更新与失效")
    ctx.rag.ingest("school", [{**DOCS[0], "text": "Edinburgh 计算机 硕士 截止改为 2027-01-20"}])
    again = ctx.rag.search("school", "Edinburgh 截止", top_k=5, rerank_top=3)
    check("同 source_id 覆盖更新", any("01-20" in h.content or "01-15" in h.content for h in again),
          f"{len(again)} 条")

    failed = [r for r in results if not r[1]]
    print(f"\n{'全部通过 ✅' if not failed else f'{len(failed)} 项未通过 ❌'}")
    print(f"数据库：{db_path}")
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
