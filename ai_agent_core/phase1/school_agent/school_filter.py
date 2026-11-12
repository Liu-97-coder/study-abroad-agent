"""RAG 智能筛选引擎（选校 Agent 步骤 2）。

三层筛选（对应文档 1.2）：
1. 标量过滤：国家 / 学位 / 语言 / 开课年份 —— 由 RAG 前置 where 完成
2. 语义召回：专业方向、背景描述
3. 硬门槛拦截：GPA 差太多直接剔除、已截止直接剔除

注意"冲刺"的判定：允许 GPA 差 0.3 以内的学校留在候选里（否则冲刺档永远为空），
差 0.3 以上才剔除 —— 这条阈值是业务规则，写在常量里方便调。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ...schema.student_schema import StudentBasicInfo
from ...utils.date_utils import days_until

GPA_REACH_TOLERANCE = 0.3      # 冲刺允许差多少 GPA
GPA_HARD_REJECT = 0.5          # 差超过这个直接剔除

# 专业方向匹配：CS 学生的清单里不该出现"金融学""传媒"
MAJOR_FAMILY_KEYWORDS = {
    "计算机": ["计算机", "数据科学", "软件", "人工智能", "信息系统", "金融科技", "数据科学"],
    "金融": ["金融", "商业分析", "会计", "经济", "投资", "金融科技"],
    "传媒": ["传媒", "传播", "新闻", "媒体"],
    "教育": ["教育", "教学", "tesol"],
    "电子工程": ["电子", "通信", "电气", "信号"],
    "机械工程": ["机械", "机电", "自动化"],
}


def _major_ok(target_major: str | None, candidate_major: str) -> bool:
    """方向不一致就剔除；无法判断（学生没写专业）时放行，避免误杀。"""
    if not target_major:
        return True
    keywords = MAJOR_FAMILY_KEYWORDS.get(target_major)
    if not keywords:
        return True
    return any(kw in (candidate_major or "") for kw in keywords)


@dataclass
class FilterResult:
    candidates: list[dict] = field(default_factory=list)
    dropped: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.candidates


def build_query(student: StudentBasicInfo) -> str:
    parts = [
        " ".join(student.target_country),
        student.target_degree or "硕士",
        student.target_major or "",
        student.major or "",
        "录取要求 GPA 语言 截止日期",
    ]
    return " ".join(p for p in parts if p)


def build_where(student: StudentBasicInfo) -> dict:
    where: dict = {}
    if student.target_country:
        where["country"] = {"$in": student.target_country}
    if student.target_degree:
        where["degree"] = student.target_degree
    return where


def filter_schools(rag, student: StudentBasicInfo, top_k: int = 40) -> FilterResult:
    result = FilterResult()
    chunks = rag.search("school", build_query(student), where=build_where(student),
                        top_k=top_k, rerank_top=top_k)
    if not chunks:
        result.warnings.append("院校库未命中：可能国家/学位组合暂无数据，需补充知识库")
        return result

    for chunk in chunks:
        meta = dict(chunk.metadata)
        name = meta.get("school_name", "")
        major = meta.get("major", "")
        source_id = chunk.source_info.get("source_id", "")

        if not source_id:
            result.warnings.append(f"{name} {major} 缺少溯源 source_id，已跳过（防幻觉）")
            continue

        if not _major_ok(student.target_major, major):
            result.dropped.append({
                "school_name": name, "major_name": major,
                "reason": f"专业方向不匹配（目标：{student.target_major}）",
            })
            continue

        gpa_min = _to_float(meta.get("gpa_min"))
        student_gpa = student.gpa
        if gpa_min is not None and student_gpa is not None:
            gap = gpa_min - student_gpa
            if gap > GPA_HARD_REJECT:
                result.dropped.append({
                    "school_name": name, "major_name": major,
                    "reason": f"GPA 差 {gap:.2f}，超出冲刺容忍范围",
                })
                continue

        left = days_until(meta.get("deadline"))
        if left is not None and left < 0:
            result.dropped.append({
                "school_name": name, "major_name": major,
                "reason": f"申请已截止（{meta.get('deadline')}）",
            })
            continue

        if gpa_min is None:
            result.warnings.append(f"{name} {major} 缺 gpa_min 字段，只能按中性处理")

        result.candidates.append({
            "school_name": name,
            "major_name": major,
            "country": meta.get("country", ""),
            "gpa_min": gpa_min,
            "ielts_min": _to_float(meta.get("ielts_min")),
            "toefl_min": _to_float(meta.get("toefl_min")),
            "gre_min": _to_float(meta.get("gre_min")),
            "bg_require": meta.get("bg_require", "普通本科"),
            "deadline": meta.get("deadline", ""),
            "days_left": left,
            "qs_rank": _to_float(meta.get("qs_rank")),
            "tuition": meta.get("tuition", ""),
            "deposit": meta.get("deposit", ""),
            "deposit_refund": meta.get("deposit_refund", ""),
            "prereq": meta.get("prereq", ""),
            "source_id": source_id,
            "source_name": chunk.source_info.get("source_name", ""),
        })

    # 同一学校同一专业可能多条分片，按 (学校, 专业) 去重
    seen, unique = set(), []
    for item in result.candidates:
        key = (item["school_name"], item["major_name"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    result.candidates = unique
    return result


def _to_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
