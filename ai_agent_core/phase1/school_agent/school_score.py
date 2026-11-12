"""冲刺 / 匹配 / 保底 三档分级算法（选校 Agent 步骤 3）。

核心不是"给个分数"，而是**可解释的录取难度指数**：

    难度指数 = 60% 项目本身录取难度（QS 排名 + 硬门槛）
             + 15% 你的 GPA 与门槛的差距
             + 10% 你的语言与门槛的差距
             +  5% 院校背景差距
             + 10% 截止紧迫度

为什么这么配：只看"学生差多少"会让 3.2 的学生看什么都是保底（不真实）；
只看"学校多难"又忽略了学生个体差异。两者加权，顾问才能看到
"这所学校本身难 + 我差 0.3 分" 这种可核对的理由。

三档线沿用文档口径：75-100 冲刺 / 50-75 匹配 / 0-50 保底。
"""
from __future__ import annotations

from ...config import settings
from ...schema.school_schema import SchoolItem
from ...schema.student_schema import StudentBasicInfo
from ...utils.score_utils import clamp

BG_SCORE = {"985": 4.0, "211": 3.5, "双一流": 3.4, "海外": 3.0, "普通本科": 2.2}

SPRINT_LINE = 75.0
MATCH_LINE = 50.0


def program_difficulty(cand: dict) -> float:
    """项目本身有多难进：QS 排名 + GPA 门槛，0-100。

    曲线是标定出来的：QS 20 内算天花板（100），50 内 90，80 内 80，
    120 内 68，200 内 56，300 内 45，其余 34。
    太陡会让"学生够线"变成保底、太平会让所有学校挤在匹配，两版都试过。
    """
    qs = cand.get("qs_rank")
    if not qs:
        base = 50.0
    elif qs <= 20:
        base = 100.0
    elif qs <= 50:
        base = 90.0
    elif qs <= 80:
        base = 80.0
    elif qs <= 120:
        base = 68.0
    elif qs <= 200:
        base = 56.0
    elif qs <= 300:
        base = 45.0
    else:
        base = 34.0
    gpa_min = cand.get("gpa_min")
    if gpa_min and gpa_min >= 3.5:
        base = min(100.0, base + 6)
    return base


def score_one(cand: dict, student: StudentBasicInfo) -> SchoolItem:
    detail: dict[str, float] = {}
    risks: list[str] = []

    # 1) 项目难度 60
    difficulty = program_difficulty(cand)
    detail["项目难度"] = round(settings.weight_program * difficulty / 100, 2)
    if difficulty >= 88:
        risks.append("竞争极大")

    # 2) GPA 差距 15（门槛比学生高 0.5 分即拉满）
    gpa, gpa_min = student.gpa, cand.get("gpa_min")
    if gpa is None or gpa_min is None:
        detail["GPA差距"] = round(settings.weight_gpa * 0.5, 2)
        risks.append("GPA数据缺失")
    else:
        gap = gpa_min - gpa
        detail["GPA差距"] = round(settings.weight_gpa * clamp((gap + 0.1) / 0.6), 2)
        if gap > 0.05:
            risks.append(f"GPA差{gap:.2f}")
        elif gap < -0.4:
            risks.append("GPA高于门槛较多（可再冲一档）")

    # 3) 语言差距 10（差 1.0 分即拉满）
    ielts, ielts_min = student.ielts, cand.get("ielts_min")
    if ielts is None:
        detail["语言差距"] = round(settings.weight_language * 0.7, 2)
        risks.append("缺语言成绩")
    elif ielts_min is None:
        detail["语言差距"] = round(settings.weight_language * 0.4, 2)
    else:
        gap = ielts_min - ielts
        detail["语言差距"] = round(settings.weight_language * clamp((gap + 0.2) / 0.8), 2)
        if gap > 0:
            risks.append(f"雅思差{gap:.1f}")

    # 4) 院校背景差距 5
    s = BG_SCORE.get(student.school_level or "普通本科", 2.2)
    r = BG_SCORE.get(str(cand.get("bg_require") or "普通本科"), 2.2)
    detail["背景差距"] = round(settings.weight_background * clamp((r - s + 0.3) / 1.5), 2)
    if s + 0.5 < r:
        risks.append("院校背景偏弱")

    # 5) 截止紧迫度 10
    days_left = cand.get("days_left")
    if days_left is None:
        detail["截止紧迫度"] = round(settings.weight_deadline * 0.5, 2)
    elif days_left <= 30:
        detail["截止紧迫度"] = float(settings.weight_deadline)
        risks.append(f"仅剩{days_left}天")
    elif days_left <= 60:
        detail["截止紧迫度"] = round(settings.weight_deadline * 0.73, 2)
        risks.append(f"距截止{days_left}天")
    elif days_left <= 120:
        detail["截止紧迫度"] = round(settings.weight_deadline * 0.4, 2)
    else:
        detail["截止紧迫度"] = round(settings.weight_deadline * 0.13, 2)

    # 软背景：不计入难度指数，只做风险提示（它影响录取概率，不改变项目难度）
    if student.internship_count == 0 and student.research_count == 0:
        risks.append("无软背景素材")

    total = round(sum(detail.values()), 1)
    level = "冲刺" if total >= SPRINT_LINE else ("匹配" if total >= MATCH_LINE else "保底")

    lang_text = f"IELTS {ielts_min:g}" if ielts_min is not None else "见官网"
    other = []
    if cand.get("gre_min"):
        other.append(f"GRE {cand['gre_min']:g}")
    if cand.get("prereq") and cand["prereq"] != "无":
        other.append(f"先修课：{cand['prereq']}")
    if cand.get("qs_rank"):
        other.append(f"QS {cand['qs_rank']:g}")

    return SchoolItem(
        school_name=cand.get("school_name", ""),
        major_name=cand.get("major_name", ""),
        country=cand.get("country", ""),
        level_type=level,
        gpa_require=f"GPA {gpa_min:g}" if gpa_min is not None else "见官网",
        lang_require=lang_text,
        other_require="；".join(other),
        deadline=cand.get("deadline", ""),
        days_left=days_left,
        risk_point="、".join(risks) if risks else "无明显短板",
        match_score=total,
        score_detail=detail,
        source_id=cand.get("source_id", ""),
    )


def split_into_three(candidates: list[dict], student: StudentBasicInfo) -> dict[str, list[SchoolItem]]:
    items = [score_one(cand, student) for cand in candidates]
    buckets: dict[str, list[SchoolItem]] = {"冲刺": [], "匹配": [], "保底": []}
    for item in items:
        buckets[item.level_type].append(item)
    for key in buckets:
        buckets[key].sort(key=lambda x: x.match_score, reverse=True)
        buckets[key] = buckets[key][:8]
    return buckets
