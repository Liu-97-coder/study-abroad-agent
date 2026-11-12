"""咨询纪要自动总结（选校 Agent 步骤 6）。

输出七段式结构化纪要，自动同步待办 —— 这一条直接解决"顾问离职交接断层"：
新人拿到纪要就知道客户要什么、顾虑什么、下一步做什么。
"""
from __future__ import annotations

import re

from ...prompt.extract_prompt import CHAT_SUMMARY_PROMPT
from ...schema.student_schema import StudentBasicInfo
from ...utils.text_clean import split_sentences

CONCERN_WORDS = ["担心", "顾虑", "怕", "不满意", "纠结", "犹豫", "但是", "不过", "问题"]
TODO_WORDS = ["下周", "明天", "需要", "请", "安排", "准备", "发我", "补充", "约定", "尽快"]


def _pick(sentences: list[str], words: list[str], limit: int = 3) -> list[str]:
    out = []
    for s in sentences:
        if any(w in s for w in words) and 4 <= len(s) <= 120:
            out.append(s)
        if len(out) >= limit:
            break
    return out


def summarize_by_rules(chat_text: str, student: StudentBasicInfo) -> dict:
    sentences = split_sentences(chat_text)
    needs = _pick(sentences, ["想申请", "希望", "目标", "想读", "计划", "要求"])
    concerns = _pick(sentences, CONCERN_WORDS)
    todos = _pick(sentences, TODO_WORDS)
    opens = [s for s in sentences if s.endswith(("吗", "呢", "？", "?"))][:3]

    return {
        "客户核心需求": needs or ["待顾问补充"],
        "学生背景梳理": [
            f"院校：{student.school_name or '未提供'} / {student.school_level or '未定'}",
            f"GPA：{student.gpa if student.gpa is not None else '未提供'}；语言：{student.ielts or student.toefl or '未提供'}",
            f"软背景：实习{student.internship_count}段、科研{student.research_count}项",
        ],
        "家长顾虑/痛点": concerns or ["本次沟通未见明显顾虑"],
        "意向信息": [
            f"国家：{'、'.join(student.target_country) or '未定'}",
            f"学位/专业：{student.target_degree or ''} {student.target_major or ''}",
            f"预算：{student.budget or '未提供'}；入学：{student.intake_year or '未定'}",
        ],
        "未解决疑问": opens or ["暂无"],
        "本次沟通共识": ["信息已记录，待顾问输出三档选校方案"],
        "下一步待办": todos or ["顾问 24 小时内输出选校方案初稿"],
    }


def render_rule_text(summary: dict) -> str:
    lines = ["## 咨询纪要"]
    for section, values in summary.items():
        lines.append(f"\n**{section}**")
        for v in values:
            lines.append(f"- {v}")
    return "\n".join(lines)


def summarize(chat_text: str, student: StudentBasicInfo, ctx,
              customer_id: str = "system") -> dict:
    rule_summary = summarize_by_rules(chat_text, student)
    fallback = render_rule_text(rule_summary)
    prompt = CHAT_SUMMARY_PROMPT.format(chat_text=(chat_text or "")[:6000])
    text = ctx.llm.text(prompt, fallback=fallback, tier="small", customer_id=customer_id)
    return {"structured": rule_summary, "markdown": text, "source": "llm" if ctx.llm.available else "rule"}
