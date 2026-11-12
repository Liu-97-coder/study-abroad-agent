"""CV 简历自动生成（文书 Agent 步骤 2）。

按专业大类切换模板侧重：商科看业务结果，计算机看技术栈与规模，
传媒看作品与传播数据，教育看教学法与课堂成效。
"""
from __future__ import annotations

from ...prompt.doc_prompt import CV_GENERATE_PROMPT
from ...schema.document_schema import StudentExperience
from ...schema.student_schema import StudentBasicInfo
from ...utils.text_clean import truncate

MAJOR_FAMILY = {
    "计算机": ["计算机", "软件", "数据", "人工智能", "cs", "computer", "ai"],
    "商科": ["金融", "会计", "商", "管理", "经济", "finance", "business", "mba"],
    "传媒": ["传媒", "新闻", "传播", "媒体", "communication", "media"],
    "教育": ["教育", "tesol", "教学", "education"],
    "工程": ["工程", "机械", "电子", "电气", "材料", "engineering"],
}

FAMILY_FOCUS = {
    "计算机": "技术栈、系统规模、性能指标（QPS/准确率/数据量）",
    "商科": "业务结果、金额规模、增长比例、团队协作",
    "传媒": "作品数量、传播数据（阅读/播放/转化）、受众反馈",
    "教育": "教学时长、学生规模、成绩提升幅度、课程设计",
    "工程": "项目规模、工艺参数、良率/效率提升、安全标准",
    "通用": "职责范围、量化结果、可迁移能力",
}


def detect_family(major: str | None) -> str:
    low = (major or "").lower()
    for family, words in MAJOR_FAMILY.items():
        if any(w in low for w in words):
            return family
    return "通用"


def _render_fallback(student: StudentBasicInfo, experiences: list[StudentExperience],
                     family: str) -> str:
    name = student.school_name or "Student"
    lines = [
        f"# {name}",
        "",
        f"*Target: {student.target_degree or 'Master'} in {student.target_major or 'TBD'}*  ",
        f"*Contact: 待补充  |  Email: 待补充*",
        "",
        "## EDUCATION",
        f"- **{student.school_name or '待补充'}** — {student.major or '待补充'}  ",
        f"  GPA: {student.gpa if student.gpa is not None else '待补充'}/4.0  "
        f"| Expected graduation: {student.intake_year or '待补充'}",
        "",
        "## RESEARCH & PROJECTS",
    ]
    sections = {"research": "## RESEARCH & PROJECTS", "internship": "## INTERNSHIP EXPERIENCE",
                "project": "## PROJECTS", "award": "## AWARDS & HONORS"}
    grouped: dict[str, list[StudentExperience]] = {}
    for exp in experiences:
        grouped.setdefault(exp.kind, []).append(exp)

    ordered = ["research", "project", "internship", "award"]
    used_headers = set()
    for kind in ordered:
        items = grouped.get(kind)
        if not items:
            continue
        header = sections[kind]
        if header not in used_headers:
            lines += ["", header]
            used_headers.add(header)
        for exp in items:
            lines.append(f"- **{truncate(exp.title, 40)}** — {exp.org or '待补充'} ({exp.time or '时间待补充'})")
            detail = exp.highlight or truncate(exp.content, 160)
            lines.append(f"  - {detail}")
    if not experiences:
        lines += ["- （暂无结构化经历，需顾问补充后再生成）"]

    lines += ["", "## SKILLS"]
    skills = sorted({s for exp in experiences for s in exp.skills})
    lines.append("- " + ("、".join(skills) if skills else "待补充"))
    lines += ["", "---",
              f"> 生成侧重：{FAMILY_FOCUS.get(family, FAMILY_FOCUS['通用'])}。"
              "离线模式输出结构骨架；接入 LLM 后输出地道英文正文。"]
    return "\n".join(lines)


def generate_cv(student: StudentBasicInfo, experiences: list[StudentExperience], ctx,
                customer_id: str = "system") -> dict:
    family = detect_family(student.target_major or student.major)
    from .experience_parse import build_experience_text

    fallback = _render_fallback(student, experiences, family)
    prompt = CV_GENERATE_PROMPT.format(
        major_family=family, experiences=build_experience_text(experiences),
        target_major=student.target_major or student.major or "未定")
    text = ctx.llm.text(prompt, fallback=fallback, tier="big", customer_id=customer_id)
    return {"content": text, "major_family": family, "source": "llm" if ctx.llm.available else "rule"}
