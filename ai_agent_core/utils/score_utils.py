"""分数换算与打分数学。"""
from __future__ import annotations


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def gpa_to_4(gpa: float | None, scale: float | None) -> float | None:
    """统一换算到 4.0 制（任务：学生信息标准化）。"""
    if gpa is None:
        return None
    scale = scale or 4.0
    if abs(scale - 4.0) < 0.01:
        return round(float(gpa), 2)
    if abs(scale - 5.0) < 0.01:
        return round(float(gpa) * 4.0 / 5.0, 2)
    if abs(scale - 100) < 0.01:
        return round(float(gpa) / 25.0, 2)
    return round(float(gpa) * 4.0 / scale, 2)


def percent_to_gpa4(score: float | None) -> float | None:
    if score is None:
        return None
    return round(float(score) / 25.0, 2)


def weighted_total(parts: dict[str, float], weights: dict[str, float]) -> float:
    return round(sum(parts.get(k, 0.0) * weights.get(k, 0.0) for k in weights), 2)


def language_gap(requirement: str | float | None, student_ielts: float | None,
                 student_toefl: int | None = None) -> float | None:
    """语言分差：正数=还差多少分。识别 'IELTS 6.5' / '6.5 (6.0)' / 纯数字。"""
    if not requirement:
        return None
    import re

    text = str(requirement)
    if student_ielts is not None:
        m = re.search(r"(?:IELTS|雅思)?\s*([4-9](?:\.\d)?)", text, re.I)
        if m:
            return round(float(m.group(1)) - float(student_ielts), 2)
    if student_toefl is not None:
        m = re.search(r"(?:TOEFL|托福)?\s*(\d{2,3})", text)
        if m and int(m.group(1)) > 9:
            return int(m.group(1)) - int(student_toefl)
    return None
