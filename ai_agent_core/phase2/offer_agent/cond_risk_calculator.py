"""Con 条件达标风险测算（Offer Agent 步骤 3）。

最实用的一段业务逻辑：学生均分 78，Offer 要 85 —— 到底还剩几门课、每门要考多少？
这里给出的是"差距 + 是否可达成"的判断，不是玄学概率。
"""
from __future__ import annotations

import re

from ...schema.offer_schema import CondCondition
from ...schema.student_schema import StudentBasicInfo


def _num(text: str) -> float | None:
    m = re.search(r"(\d{1,3}(?:\.\d+)?)", text or "")
    return float(m.group(1)) if m else None


def assess(cond: CondCondition, student: StudentBasicInfo) -> CondCondition:
    require = _num(cond.require_value)

    if cond.cond_type == "均分" and require is not None:
        current = student.average_score
        if current is None and student.gpa is not None:
            current = round(student.gpa * 25, 1)
        cond.current_student_value = f"{current}%" if current is not None else "未提供"
        if current is None:
            cond.reach_risk, cond.gap = "中", "缺少当前均分"
            cond.improve_suggest = "补充当前均分与剩余课程学分，才能测算"
        else:
            gap = round(require - current, 1)
            cond.gap = f"差 {gap} 分"
            if gap <= 0:
                cond.reach_risk = "低"
                cond.improve_suggest = "已达标，注意最后一学期别掉档，保住在读成绩"
            elif gap <= 3:
                cond.reach_risk = "中"
                cond.improve_suggest = "剩余课程保持 85+ 可达成，避开低分选修课"
            else:
                cond.reach_risk = "高"
                cond.improve_suggest = "差距较大，考虑重修低分课程 + 同步加申 2 所保底校"

    elif cond.cond_type == "语言" and require is not None:
        current = student.ielts or (round((student.toefl or 0) / 11.9, 1) if student.toefl else None)
        cond.current_student_value = f"{current}" if current else "未提供"
        if not current:
            cond.reach_risk, cond.gap = "高", "无语言成绩"
            cond.improve_suggest = "立即报名雅思，按最短出分周期倒排（通常 4-6 周）"
        else:
            gap = round(require - current, 1)
            cond.gap = f"差 {gap} 分"
            if gap <= 0:
                cond.reach_risk = "低"
                cond.improve_suggest = "已达标，确认成绩单在 2 年有效期内"
            elif gap <= 0.5:
                cond.reach_risk = "中"
                cond.improve_suggest = "差 0.5 分，报 1 次冲刺考 + 同步确认语言班方案"
            else:
                cond.reach_risk = "高"
                cond.improve_suggest = "差距明显，优先锁定语言班（注意语言班也有截止日）"

    elif cond.cond_type == "GRE":
        current = student.gre
        cond.current_student_value = str(current) if current else "未提供"
        if not current:
            cond.reach_risk = "高"
            cond.improve_suggest = "确认该项目是否强制 GRE，若强制需预留 3 个月备考"
        else:
            cond.reach_risk = "低" if current >= (require or 0) else "中"
            cond.improve_suggest = "可持续刷分或补充量化背景"
    else:
        cond.reach_risk = cond.reach_risk or "中"
        cond.current_student_value = cond.current_student_value or "见档案"
        cond.improve_suggest = cond.improve_suggest or "按 Offer 原文逐条核对，必要时邮件问 admissions"
    return cond


def assess_all(conditions: list[CondCondition], student: StudentBasicInfo) -> tuple[list[CondCondition], str]:
    assessed = [assess(CondCondition(**c.model_dump()), student) for c in conditions]
    levels = {c.reach_risk for c in assessed}
    overall = "高" if "高" in levels else ("中" if "中" in levels else "低")
    return assessed, overall
