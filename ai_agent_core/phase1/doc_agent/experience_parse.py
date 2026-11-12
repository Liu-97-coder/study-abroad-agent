"""学生经历结构化解析（文书 Agent 步骤 1）。

文书质量的上限由素材决定：先把"教育/实习/科研/竞赛"拆成结构化条目，
每条补上"做了什么 + 结果如何（量化）+ 用到什么技能"，SOP 才可能写出个性化文书。
"""
from __future__ import annotations

import re

from ...schema.document_schema import StudentExperience
from ...utils.text_clean import split_sentences

KIND_RULES = {
    "internship": ["实习", "intern", "工作", "任职"],
    "research": ["科研", "论文", "实验", "研究", "实验室", "课题"],
    "project": ["项目", "开发", "系统", "课程设计"],
    "award": ["竞赛", "获奖", "奖学金", "一等奖", "二等奖", "金奖", "排名"],
    "education": ["大学", "学院", "本科", "硕士", "就读", "GPA"],
}

ORG_HINT = ["公司", "集团", "科技", "银行", "证券", "研究院", "实验室", "大学", "学院", "事务所"]
TIME_PATTERN = re.compile(r"(20\d{2}[./\-年]\d{1,2}[月]?)\s*[-–—至~]\s*(20\d{2}[./\-年]\d{1,2}[月]?|至今|现在)")
QUANT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(%|万|人|次|个|项|倍|小时|条|篇|台)")


def classify(text: str) -> str:
    for kind, words in KIND_RULES.items():
        if any(w in text for w in words):
            return kind
    return "project"


def extract_highlight(text: str) -> str:
    """优先挑带数字的句子当亮点（无量化不成文书）。"""
    for sentence in split_sentences(text):
        if QUANT_PATTERN.search(sentence):
            return sentence[:120]
    return ""


def parse_experiences(raw: str | list, student_name: str = "") -> list[StudentExperience]:
    """支持两种输入：一段自由文本，或前端/中台已结构化的 list。"""
    results: list[StudentExperience] = []

    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                results.append(StudentExperience(**{
                    k: v for k, v in item.items() if k in StudentExperience.model_fields}))
            elif isinstance(item, str):
                results.append(_one(item))
        return [r for r in results if r.content or r.title]

    text = str(raw or "")
    if not text.strip():
        return []

    blocks = re.split(r"[\n]+|(?<=[。！？])\s*(?=\d+[.、])", text)
    for block in blocks:
        block = block.strip()
        if len(block) < 8:
            continue
        results.append(_one(block))
    return results


def _one(block: str) -> StudentExperience:
    kind = classify(block)
    time_match = TIME_PATTERN.search(block)
    org = ""
    for hint in ORG_HINT:
        m = re.search(rf"([\u4e00-\u9fa5A-Za-z]{{2,20}}{hint})", block)
        if m:
            org = m.group(1)
            break
    title = block[:24].replace("\n", " ")
    return StudentExperience(
        title=title,
        org=org,
        time=time_match.group(0) if time_match else "",
        content=block[:400],
        highlight=extract_highlight(block),
        skills=[m.group(0) for m in re.finditer(r"(Python|SQL|Excel|Java|R|SPSS|Tableau|Figma|C\+\+|机器学习|数据分析)", block)],
        kind=kind,
    )


def build_experience_text(experiences: list[StudentExperience]) -> str:
    """压成给 Prompt 用的紧凑文本，控制 token。"""
    if not experiences:
        return "（学生暂无结构化经历，需顾问补充）"
    lines = []
    for i, exp in enumerate(experiences, 1):
        lines.append(f"{i}. [{exp.kind}] {exp.title} @ {exp.org or '未注明单位'} {exp.time}")
        lines.append(f"   内容：{exp.content}")
        if exp.highlight:
            lines.append(f"   亮点：{exp.highlight}")
    return "\n".join(lines)
