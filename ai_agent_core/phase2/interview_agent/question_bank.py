"""面试题库：结构化 JSON + RAG 检索，按专业/国家/类型挑题。

两种取题方式：
1. RAG 检索（writing 库里的 interview 文档，带 qid 元数据）—— 体现"素材库驱动"
2. 本地 JSON 过滤 —— RAG 没命中（比如没灌库）时的兜底
"""
from __future__ import annotations

import json
from pathlib import Path

from ...config import SEED_DIR
from ...schema.interview_schema import InterviewQuestion
from ...schema.student_schema import StudentBasicInfo

CATEGORY_ORDER = ["动机", "学术", "实习", "行为", "思辨", "院校", "团队", "职业", "收尾"]
BANK_FILE = "interview_questions.json"


def load_bank() -> list[InterviewQuestion]:
    path = Path(SEED_DIR) / BANK_FILE
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [InterviewQuestion(**{**q, "source_id": q.get("qid", "")})
            for q in data.get("questions", [])]


def _match(q: InterviewQuestion, major: str, country: str) -> bool:
    major_ok = q.major in {"通用", major} or (major and major in q.major)
    country_ok = q.country in {"通用", country} or (country and country in q.country)
    return major_ok and country_ok


def _dedupe(items: list[InterviewQuestion]) -> list[InterviewQuestion]:
    seen, out = set(), []
    for item in items:
        if item.qid in seen:
            continue
        seen.add(item.qid)
        out.append(item)
    return out


def _arrange(items: list[InterviewQuestion], count: int) -> list[InterviewQuestion]:
    """保证题型有梯度：先每类各来一题，再按输入顺序补齐，最后按类别排序。

    只按检索相似度取前 N 题，会抽出 3 道学术题 —— 面试官不会这么问。
    """
    pool = _dedupe(items)
    by_cat: dict[str, list[InterviewQuestion]] = {}
    for q in pool:
        by_cat.setdefault(q.category, []).append(q)

    picked: list[InterviewQuestion] = []
    for category in CATEGORY_ORDER:
        if len(picked) >= count:
            break
        bucket = by_cat.get(category) or []
        if bucket:
            picked.append(bucket.pop(0))
    for q in pool:
        if len(picked) >= count:
            break
        if q not in picked:
            picked.append(q)

    picked.sort(key=lambda q: CATEGORY_ORDER.index(q.category)
                if q.category in CATEGORY_ORDER else 99)
    return picked[:count]


def pick_from_bank(student: StudentBasicInfo, count: int = 6) -> list[InterviewQuestion]:
    """按专业/国家过滤，再按"动机→学术→实习→行为→思辨→收尾"的顺序铺开。"""
    major = student.target_major or ""
    country = (student.target_country or [""])[0]
    pool = [q for q in load_bank() if _match(q, major, country)]
    if not pool:
        pool = load_bank()
    return _arrange(pool, count)


def pick_with_rag(ctx, student: StudentBasicInfo, count: int = 6) -> list[InterviewQuestion]:
    """先让 RAG 按"目标专业 + 面试"召回，再用 qid 回表拿结构化字段。

    RAG 只负责"相关性"，题型梯度交给 _arrange —— 两者职责分开。
    """
    if ctx is None:
        return pick_from_bank(student, count)

    query = (f"{student.target_major or ''} {student.major or ''} "
             f"{' '.join(student.target_country) if student.target_country else ''} 面试题 考察点")
    chunks = ctx.rag.search("writing", query, where={"type": "interview"},
                            top_k=count * 3, rerank_top=count * 2)
    bank = {q.qid: q for q in load_bank()}

    candidates: list[InterviewQuestion] = []
    for chunk in chunks:
        qid = str(chunk.metadata.get("qid") or "")
        item = bank.get(qid)
        if item is not None:
            candidates.append(item.model_copy(update={"source_id": qid}))

    # 用题库补齐，保证题型覆盖不依赖检索运气
    candidates += pick_from_bank(student, count * 3)
    return _arrange(candidates, count)


def build_interview_docs() -> list[dict]:
    """给 ingest_seed 用：把题库灌进 writing 库（type=interview）。"""
    docs = []
    for q in load_bank():
        text = (f"面试题（{q.category}）：{q.question}\n"
                f"考察点：{q.focus}\n参考要点：{q.hints}\n"
                f"适用专业：{q.major}；适用国家：{q.country}；难度：{q.difficulty}")
        docs.append({
            "text": text,
            "metadata": {"type": "interview", "qid": q.qid, "category": q.category,
                         "major": q.major, "country": q.country,
                         "difficulty": q.difficulty},
            "source_id": f"interview:{q.qid}",
            "source_name": "面试题库（示例）",
            "update_time": "2026-11-01",
        })
    return docs
