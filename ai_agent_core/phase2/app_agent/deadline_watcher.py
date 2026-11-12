"""截止日期三级倒计时预警（网申 Agent 步骤 3）。

30 天常规提醒 → 15 天加急 → 7 天高危推送主管与负责人。
已递交专业自动剔除，避免重复轰炸。
"""
from __future__ import annotations

from ...utils.date_utils import days_until

TIERS = [(7, "三级高危", "主管+负责人", 3), (15, "二级加急", "顾问+主管", 2),
         (30, "一级提醒", "顾问", 1)]


def watch(programs: list[dict]) -> list[dict]:
    """programs: [{school, major, deadline, submitted}]"""
    warnings = []
    for program in programs:
        if program.get("submitted"):
            continue
        left = days_until(program.get("deadline"))
        if left is None or left < 0:
            continue
        for days, label, audience, rank in TIERS:
            if left <= days:
                warnings.append({
                    "school": program.get("school", ""),
                    "major": program.get("major", ""),
                    "deadline": program.get("deadline", ""),
                    "days_left": left,
                    "tier": label,
                    "notify": audience,
                    "rank": rank,
                })
                break
    warnings.sort(key=lambda x: (-x["rank"], x["days_left"]))
    return warnings


def from_school_result(school_result: dict, submitted: list[str] | None = None) -> list[dict]:
    """把选校方案的截止日期直接转成监控列表。"""
    submitted = submitted or []
    programs = []
    for key in ("sprint_list", "match_list", "safe_list"):
        for item in school_result.get(key, []) or []:
            programs.append({
                "school": item.get("school_name", ""),
                "major": item.get("major_name", ""),
                "deadline": item.get("deadline", ""),
                "submitted": item.get("school_name", "") in submitted,
            })
    return watch(programs)
