"""日期解析与倒计时。死线计算的唯一入口，避免各 Agent 各写一套。"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

_DATE_PATTERNS = [
    (re.compile(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})"), lambda m: date(int(m[1]), int(m[2]), int(m[3]))),
    (re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日"), lambda m: date(int(m[1]), int(m[2]), int(m[3]))),
    (re.compile(r"(\d{4})[-/.](\d{1,2})"), lambda m: date(int(m[1]), int(m[2]), 1)),
    (re.compile(r"(\d{4})年(\d{1,2})月"), lambda m: date(int(m[1]), int(m[2]), 1)),
]


def parse_date(value: str | date | None) -> date | None:
    """把各种写法的日期转成 date；解析不了返回 None（绝不瞎猜）。"""
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = str(value).strip()
    for pattern, builder in _DATE_PATTERNS:
        m = pattern.search(text)
        if m:
            try:
                return builder(m)
            except ValueError:
                continue
    return None


def days_until(value: str | date | None, today: date | None = None) -> int | None:
    """距今天还有多少天；负数表示已过期。"""
    target = parse_date(value)
    if target is None:
        return None
    return (target - (today or date.today())).days


def fmt_date(value: str | date | None) -> str:
    d = parse_date(value)
    return d.isoformat() if d else ""


def add_days(value: str | date | None, days: int) -> str:
    d = parse_date(value) or date.today()
    return (d + timedelta(days=days)).isoformat()


def academic_window(intake_year: int | None, today: date | None = None) -> dict:
    """申请时间窗口分析：给评估报告用。"""
    today = today or date.today()
    if not intake_year:
        return {"window": "未知", "months_left": None, "urgent": False}
    months_left = (intake_year - today.year) * 12 + (9 - today.month)
    urgent = months_left <= 6
    window = "充足" if months_left > 12 else ("偏紧" if months_left > 6 else "紧张")
    return {"window": window, "months_left": months_left, "urgent": urgent}
