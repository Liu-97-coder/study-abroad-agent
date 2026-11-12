"""PS 个人陈述生成（文书 Agent 步骤 3，一期最难的一段）。

写作逻辑链固定六段：学术启蒙 → 课程基础 → 科研深度 → 实习能力 → 院校匹配 → 职业规划。
"院校匹配"这一段必须引用 RAG 检索到的目标专业课程，否则就是通用套话。
"""
from __future__ import annotations

from ...prompt.doc_prompt import PS_GENERATE_PROMPT
from ...schema.document_schema import StudentExperience
from ...schema.student_schema import StudentBasicInfo

SECTION_PLAN = [
    ("学术启蒙", "为什么选择这个专业：一个具体触发点 + 你的问题意识"),
    ("课程基础", "本科哪些课程/方法支撑你读这个硕士"),
    ("科研深度", "科研/项目经历：问题、方法、结果、你的贡献"),
    ("实习能力", "实习经历：行业理解 + 可迁移能力"),
    ("院校匹配", "目标院校的具体课程/师资/项目，为什么非它不可"),
    ("职业规划", "短期与长期目标，如何闭环回本专业"),
]


def _bind(experiences: list[StudentExperience], kind: str) -> str:
    items = [e for e in experiences if e.kind == kind]
    if not items:
        return "（该段暂无真实经历支撑，需顾问补充素材，禁止编造）"
    return "；".join(f"{e.title}（{e.org or '单位待补'}）{e.highlight or e.content[:60]}" for e in items[:2])


def _render_outline(student: StudentBasicInfo, experiences: list[StudentExperience],
                    course_context: str) -> str:
    lines = [f"# Personal Statement 写作大纲 · {student.target_major or student.major or '目标专业'}",
             "", "> 离线模式产出的是「六段式结构 + 真实经历绑定」，用于顾问/文书老师快速起稿。",
             ""]
    bindings = {
        "学术启蒙": f"{student.major or '本科专业'} 的学习经历；触发点需顾问补充 1 个具体场景",
        "课程基础": f"本科课程与 {student.target_major or '目标专业'} 的衔接（GPA "
                    f"{student.gpa if student.gpa is not None else '待补'}）",
        "科研深度": _bind(experiences, "research"),
        "实习能力": _bind(experiences, "internship"),
        "院校匹配": "从下方 RAG 课程素材中选 2 门课 + 1 个项目说明匹配原因",
        "职业规划": f"短期：{student.target_major or '目标专业'} 相关岗位；长期：需顾问与学生对齐",
    }
    for idx, (title, hint) in enumerate(SECTION_PLAN, 1):
        lines += [f"## {idx}. {title}", f"- 写作要点：{hint}", f"- 可绑定素材：{bindings[title]}", ""]
    lines += ["## RAG 检索到的目标专业课程素材", course_context, ""]
    lines += ["---", "> 强制约束：所有经历、数字、奖项必须来自学生真实材料；无素材的段落留空待补，不许编造。"]
    return "\n".join(lines)


def generate_ps(student: StudentBasicInfo, experiences: list[StudentExperience], ctx,
                customer_id: str = "system") -> dict:
    from .experience_parse import build_experience_text

    query = f"{student.target_major or ''} {student.target_country[0] if student.target_country else ''} 课程 培养目标"
    chunks = ctx.rag.search("writing", query, top_k=10, rerank_top=4)
    context = ctx.rag.format_context(chunks, max_chars=2500)
    sources = [c.source_info.get("source_id", "") for c in chunks]

    fallback = _render_outline(student, experiences, context)
    prompt = PS_GENERATE_PROMPT.format(
        experiences=build_experience_text(experiences), context=context,
        student=str(student.to_prompt_dict()))
    text = ctx.llm.text(prompt, fallback=fallback, tier="big", customer_id=customer_id)
    return {"content": text, "sources": sources,
            "source": "llm" if ctx.llm.available else "rule"}
