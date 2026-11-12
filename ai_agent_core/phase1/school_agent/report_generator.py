"""AI 背景评估报告（选校 Agent 步骤 4）。

规则先算出"事实骨架"（硬件、优势、短板、窗口、难度评级、建议），
LLM 只负责把这些事实写成顾问口吻的报告 —— 数字全部来自规则与 RAG，
模型没有机会编造分数线和截止日期。
"""
from __future__ import annotations

from ...prompt.school_prompt import STUDENT_REPORT_PROMPT
from ...schema.school_schema import SchoolResult
from ...schema.state_schema import CustomerState
from ...schema.student_schema import StudentBasicInfo
from ...utils.date_utils import academic_window


def difficulty_rating(buckets: dict[str, list], student: StudentBasicInfo) -> str:
    sprint = len(buckets.get("冲刺", []))
    safe = len(buckets.get("保底", []))
    if student.gpa is None:
        return "待定"
    if student.gpa >= 3.7 and (student.ielts or 0) >= 7.0:
        return "低"
    if sprint >= 3 or safe == 0:
        return "高"
    if student.gpa >= 3.3:
        return "中"
    return "偏高"


def build_facts(student: StudentBasicInfo, result: SchoolResult) -> dict:
    window = academic_window(student.intake_year)

    advantages = []
    if student.gpa is not None and student.gpa >= 3.5:
        advantages.append(f"GPA {student.gpa}/4.0，具备名校硬门槛竞争力")
    if (student.ielts or 0) >= 7.0:
        advantages.append(f"雅思 {student.ielts}，语言不是短板")
    if student.school_level in {"985", "211", "双一流"}:
        advantages.append(f"{student.school_level} 背景，院校认可度高")
    if student.internship_count >= 2:
        advantages.append(f"{student.internship_count} 段实习，文书写实有素材")
    if student.research_count >= 1:
        advantages.append("有科研/项目经历，可支撑学术动机")

    shortages = list(student.risk_tags)
    if not result.safe_list:
        shortages.append("保底档院校缺失（选校结构失衡）")
    if result.filtered_out:
        shortages.append(f"{len(result.filtered_out)} 所院校因硬门槛被剔除")

    suggestions = []
    if "无语言成绩" in student.risk_tags or "语言成绩偏低" in student.risk_tags:
        suggestions.append("优先安排雅思/托福考试，语言是当前最大不确定性")
    if "GPA偏低" in student.risk_tags:
        suggestions.append("剩余学期重点提均分，部分院校看最后两年成绩")
    if "无软背景" in student.risk_tags:
        suggestions.append("补 1 段与目标专业强相关的实习或科研，否则文书无差异化素材")
    if "时间紧张" in student.risk_tags or window["urgent"]:
        suggestions.append("按最早截止批次倒排，先递交 2-3 所匹配校保底")
    if not result.safe_list:
        suggestions.append("扩大国家范围或增加 1 年制项目，补齐保底档")

    return {
        "hardware": {
            "院校": f"{student.school_level or '未知'} {student.school_name or ''}".strip(),
            "专业": student.major or "未提供",
            "GPA": f"{student.gpa}/4.0" if student.gpa else "未提供",
            "语言": f"IELTS {student.ielts}" if student.ielts else (
                f"TOEFL {student.toefl}" if student.toefl else "未提供"),
            "软背景": f"实习{student.internship_count}段 / 科研{student.research_count}项 / 奖项{student.award_count}个",
            "意向": f"{'/'.join(student.target_country) or '未定'} · {student.target_degree or ''} · "
                    f"{student.target_major or ''}",
            "预算": student.budget or "未提供",
            "入学": f"{student.intake_year or '未定'} 年",
        },
        "advantages": advantages or ["暂无明显强项，需通过文书与选校策略弥补"],
        "shortages": shortages or ["暂无明显短板"],
        "window": window,
        "difficulty": difficulty_rating(
            {"冲刺": result.sprint_list, "匹配": result.match_list, "保底": result.safe_list}, student),
        "suggestions": suggestions or ["背景较均衡，可按标准节奏推进"],
        "counts": {"冲刺": len(result.sprint_list), "匹配": len(result.match_list),
                   "保底": len(result.safe_list)},
    }


def render_markdown(student: StudentBasicInfo, result: SchoolResult, facts: dict) -> str:
    lines = [f"# 留学背景评估报告 · {student.school_name or '学生'}", ""]
    lines.append("## 一、硬件条件")
    for key, value in facts["hardware"].items():
        lines.append(f"- **{key}**：{value}")
    lines += ["", "## 二、申请优势"]
    lines += [f"- {a}" for a in facts["advantages"]]
    lines += ["", "## 三、短板与风险"]
    lines += [f"- {s}" for s in facts["shortages"]]
    lines += ["", "## 四、时间窗口"]
    window = facts["window"]
    lines.append(f"- 距目标入学约 **{window['months_left']}** 个月，窗口评估：**{window['window']}**")
    lines += ["", f"## 五、整体难度评级：**{facts['difficulty']}**", ""]
    lines.append("## 六、选校结构")
    for level in ("冲刺", "匹配", "保底"):
        items = getattr(result, {"冲刺": "sprint_list", "匹配": "match_list", "保底": "safe_list"}[level])
        lines.append(f"- **{level}**（{len(items)} 所）：" + ("、".join(
            f"{i.school_name} {i.major_name}（{i.match_score}）" for i in items) or "暂无"))
    lines += ["", "## 七、行动建议"]
    lines += [f"{i}. {s}" for i, s in enumerate(facts["suggestions"], 1)]
    lines += ["", "---", f"> 数据来源：留学知识库 RAG 检索（{len(result.sources)} 条，含 source_id 可溯源）。"
                        "本报告由 AI 生成，仅作顾问决策参考，最终方案须顾问人工确认。"]
    return "\n".join(lines)


def generate_report(student: StudentBasicInfo, result: SchoolResult, ctx,
                    customer_id: str = "system") -> dict:
    facts = build_facts(student, result)
    fallback = render_markdown(student, result, facts)

    context = "\n".join(f"- {s}" for s in result.sources[:10]) or "（无检索来源）"
    prompt = STUDENT_REPORT_PROMPT.format(
        student=str(student.to_prompt_dict()), context=context)
    text = ctx.llm.text(prompt, fallback=fallback, tier="big", customer_id=customer_id)
    return {"markdown": text, "facts": facts, "source": "llm" if ctx.llm.available else "rule"}
