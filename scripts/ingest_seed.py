"""知识库灌库脚本（基座任务 1 的落地入口）。

用法：
    python scripts/ingest_seed.py            # 全量重建
    python scripts/ingest_seed.py --append   # 增量追加

做四件事：
1. 院校 CSV → school 库（结构化字段进 metadata，做标量过滤）
2. 签证政策 MD → visa 库（自适应分片 + source_id 溯源）
3. 文书素材 MD → writing 库
4. 合规词库 + 话术模板 → compliance 库
"""
from __future__ import annotations

import argparse
import csv
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
from ai_agent_core.config import SEED_DIR, settings  # noqa: E402

NUMERIC = {"qs_rank", "gpa_min", "ielts_min", "toefl_min", "gre_min", "valid_year"}


def load_schools(ctx) -> int:
    path = SEED_DIR / "universities.csv"
    if not path.exists():
        print(f"[skip] 缺少 {path}")
        return 0
    rows = []
    with path.open("r", encoding="utf-8-sig", newline="") as fp:
        for idx, row in enumerate(csv.DictReader(fp), 1):
            meta = {}
            for key, value in row.items():
                if key is None:
                    continue
                value = (value or "").strip()
                if key in NUMERIC:
                    meta[key] = float(value) if value else None
                else:
                    meta[key] = value
            text = (
                f"{meta.get('school_name')}（{meta.get('country')}）"
                f"{meta.get('major')} {meta.get('degree')}项目；"
                f"GPA 要求 {meta.get('gpa_min')}，雅思 {meta.get('ielts_min')}，"
                f"托福 {meta.get('toefl_min')}；申请截止 {meta.get('deadline')}；"
                f"学费 {meta.get('tuition')}；押金 {meta.get('deposit')}"
                f"（{meta.get('deposit_refund')}）；先修课：{meta.get('prereq') or '无'}；"
                f"QS 排名 {meta.get('qs_rank')}；背景要求 {meta.get('bg_require')}。"
            )
            rows.append({
                "text": text,
                "metadata": meta,
                "source_id": f"school-{idx:04d}",
                "source_name": "universities.csv（示例院校库）",
                "update_time": "2026-11-01",
                "valid_year": int(meta.get("valid_year") or 2027),
            })
    count = ctx.rag.ingest("school", rows, replace=True)
    print(f"[ok] school 库导入 {count} 条院校专业记录")
    return count


def load_markdown(ctx) -> int:
    total = 0
    mapping = {
        "visa_policies.md": ("visa", {"type": "visa_policy", "valid_year": 2027},
                             "签证政策库（示例）"),
        "writing_templates.md": ("writing", {"type": "writing_material"}, "文书素材库（示例）"),
    }
    for filename, (collection, meta, source_name) in mapping.items():
        path = SEED_DIR / filename
        if not path.exists():
            print(f"[skip] 缺少 {path}")
            continue
        count = ctx.rag.ingest_file(collection, path, source_name=source_name,
                                    metadata=meta, size=520, overlap=100)
        print(f"[ok] {collection} 库导入 {count} 个分片（{filename}）")
        total += count
    return total


def load_compliance(ctx) -> int:
    path = SEED_DIR / "compliance_words.json"
    if not path.exists():
        print(f"[skip] 缺少 {path}")
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    docs = []
    for idx, item in enumerate(data.get("talk_templates", []), 1):
        docs.append({
            "text": f"场景：{item.get('intent')}。合规话术模板：{item.get('text')}",
            "metadata": {"type": "talk_template", "intent": item.get("intent")},
            "source_id": f"compliance-talk-{idx:02d}",
            "source_name": "内控话术库（示例）",
            "update_time": "2026-11-01",
        })
    for idx, rule in enumerate(data.get("refund_rules", []), 1):
        docs.append({
            "text": f"退费规则：{rule}",
            "metadata": {"type": "refund_rule"},
            "source_id": f"compliance-refund-{idx:02d}",
            "source_name": "内控退费规则（示例）",
            "update_time": "2026-11-01",
        })
    forbidden = "、".join(data.get("forbidden_words", []))
    docs.append({
        "text": f"违规话术关键词清单：{forbidden}。以上表述一律不得出现在顾问对外沟通与宣传中。",
        "metadata": {"type": "forbidden_words"},
        "source_id": "compliance-words-01",
        "source_name": "违规词库（示例）",
        "update_time": "2026-11-01",
    })
    count = ctx.rag.ingest("compliance", docs, replace=True)
    print(f"[ok] compliance 库导入 {count} 条（话术模板/退费规则/违规词）")
    return count


def load_interview(ctx) -> int:
    """面试题库 → writing 库（metadata.type=interview，带 qid 便于回表）。"""
    from ai_agent_core.phase2.interview_agent.question_bank import build_interview_docs

    docs = build_interview_docs()
    if not docs:
        print("[skip] 面试题库为空")
        return 0
    count = ctx.rag.ingest("writing", docs, replace=False)
    print(f"[ok] writing 库导入 {count} 道面试题（interview_questions.json）")
    return count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--append", action="store_true", help="增量追加，不清空已有数据")
    args = parser.parse_args()

    ctx = get_context()
    print(f"RAG 后端：{settings.rag_backend} | Embedding：{settings.embed_backend} "
          f"({settings.embed_dim} 维)")
    total = load_schools(ctx) + load_markdown(ctx) + load_compliance(ctx) + load_interview(ctx)
    print(f"\n[done] 共写入 {total} 条知识，各库统计：{ctx.rag.stats()}")
    if total == 0:
        print("[warn] 一条都没导入，检查 data/seed/ 下的文件是否存在")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
