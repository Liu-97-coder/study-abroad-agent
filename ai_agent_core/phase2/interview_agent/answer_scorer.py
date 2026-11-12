"""面试回答评分：五维规则打分 + 可选 LLM 复核。

五个维度（各 0-100）：
    结构（STAR） 25   —— 有没有"背景/行动/结果"的骨架
    具体性       20   —— 长度是否够、有没有细节（人名/项目名/场景）
    量化         20   —— 数字、百分比、规模
    专业匹配     20   —— 是否覆盖题目考察点里的关键词
    表达         15   —— 句子完整、少口头禅、有逻辑连接词

规则分的意义：学生练 10 遍，每遍都能立刻看到"量化那一项还是 20 分"，比一句"多练练"有用。
"""
from __future__ import annotations

import re

from ...schema.interview_schema import AnswerScore, InterviewQuestion

DIMENSIONS = {"结构": 25, "具体性": 20, "量化": 20, "专业匹配": 20, "表达": 15}

STAR_WORDS = ["背景", "当时", "任务", "负责", "行动", "我做了", "首先", "然后", "最后",
              "结果", "最终", "because", "situation", "task", "action", "result", "so"]
FILLER_WORDS = ["嗯", "那个", "就是", "然后然后", "反正", "差不多", "应该是吧", "大概可能"]
CONNECTIVES = ["因此", "所以", "但是", "同时", "另外", "具体来说", "例如",
               "however", "therefore", "for example", "moreover"]
QUANT_PATTERN = re.compile(r"\d+(?:\.\d+)?\s*(?:%|％|万|k|w|条|人|次|个|项|倍|小时|分钟|天|年)")


def _structure_score(text: str) -> float:
    hits = sum(1 for w in STAR_WORDS if w.lower() in text.lower())
    return min(100.0, 30 + hits * 12)


def _specificity_score(text: str) -> float:
    length = len(text)
    if length < 30:
        base = 20
    elif length < 80:
        base = 55
    elif length <= 600:
        base = 85
    else:
        base = 70        # 太长通常没重点
    detail = len(re.findall(r"[A-Za-z]{3,}|[\u4e00-\u9fa5]{4,}", text))
    return min(100.0, base + min(15, detail // 12))


def _quant_score(text: str) -> float:
    hits = len(QUANT_PATTERN.findall(text))
    if hits == 0:
        return 25.0
    return min(100.0, 50 + hits * 18)


def _major_score(text: str, question: InterviewQuestion) -> float:
    keywords = [w for w in re.split(r"[、，,；;\s]+", question.focus + " " + question.hints) if len(w) >= 2]
    if not keywords:
        return 60.0
    low = text.lower()
    hits = sum(1 for k in keywords if k.lower() in low)
    return min(100.0, 35 + hits * 15)


def _expression_score(text: str) -> float:
    if not text.strip():
        return 0.0
    sentences = [s for s in re.split(r"[。！？.!?；;]+", text) if s.strip()]
    avg_len = len(text) / max(1, len(sentences))
    score = 80.0
    if avg_len > 90:
        score -= 15       # 一逗到底
    if avg_len < 8:
        score -= 10       # 太碎
    filler = sum(text.count(w) for w in FILLER_WORDS)
    score -= min(30, filler * 6)
    if any(c in text for c in CONNECTIVES):
        score += 10
    return max(0.0, min(100.0, score))


def score_answer(question: InterviewQuestion, answer: str, ctx=None,
                 customer_id: str = "") -> AnswerScore:
    text = (answer or "").strip()
    if not text:
        return AnswerScore(qid=question.qid, total=0.0, dimensions={k: 0.0 for k in DIMENSIONS},
                           feedback=["没有作答"], suggestion="先按 STAR 写一版草稿，哪怕中文也行")

    dims = {
        "结构": round(_structure_score(text), 1),
        "具体性": round(_specificity_score(text), 1),
        "量化": round(_quant_score(text), 1),
        "专业匹配": round(_major_score(text, question), 1),
        "表达": round(_expression_score(text), 1),
    }
    total = round(sum(dims[k] * w for k, w in DIMENSIONS.items()) / 100, 1)

    feedback, suggestions = [], []
    if dims["结构"] < 60:
        feedback.append("缺少清晰的 STAR 结构")
        suggestions.append("按「背景一句话 → 我的任务 → 我做的 2-3 个动作 → 结果」重写")
    if dims["量化"] < 50:
        feedback.append("几乎没有数字")
        suggestions.append("补一个规模（数据量/人数）和一个结果（提升百分比/节省时间）")
    if dims["具体性"] < 60:
        feedback.append("内容偏空或过短")
        suggestions.append("补项目名、你的具体职责、遇到的问题")
    if dims["专业匹配"] < 55:
        feedback.append("没有回应题目的考察点")
        suggestions.append(f"这题考的是「{question.focus}」，答题时要正面回应")
    if dims["表达"] < 60:
        feedback.append("口语化/句子过长")
        suggestions.append("拆短句，去掉「嗯、那个、就是」")
    if not feedback:
        feedback.append("结构、细节、量化都到位")
        suggestions.append("再压缩到 90 秒能讲完，准备一个追问版本")

    # 有真实模型时做一次语义复核（不改硬指标，只补建议）
    if ctx is not None and getattr(ctx.llm, "available", False):
        prompt = (
            f"这是一道留学面试题：{question.question}\n考察点：{question.focus}\n"
            f"学生回答：{text[:1200]}\n"
            '请用 JSON 给 1 条最关键的改进建议：{"suggestion": "..."}'
        )
        data = ctx.llm.json(prompt, fallback=None, tier="small", customer_id=customer_id)
        if isinstance(data, dict) and data.get("suggestion"):
            suggestions = [str(data["suggestion"])[:200]] + suggestions[:2]

    return AnswerScore(qid=question.qid, total=total, dimensions=dims, feedback=feedback,
                       suggestion="；".join(suggestions[:2]), answer_preview=text[:80])


def build_report(session, score_line: float = 60.0) -> str:
    """复盘报告：平均分 + 每题简评 + 三条优先改进项。"""
    questions = {q.qid: q for q in session.questions}
    lines = [f"# 模拟面试复盘 · {session.target or '目标专业'}", ""]
    lines.append(f"- 场次：`{session.session_id}`")
    lines.append(f"- 题目数：{len(session.questions)}，已答：{len(session.answers)}")
    lines.append(f"- 平均分：**{session.avg_score}**（及格线 {score_line}）")
    if session.answers:
        weakest = sorted(session.answers, key=lambda a: a.total)[:3]
        lines += ["", "## 最需要补的三题"]
        for a in weakest:
            q = questions.get(a.qid)
            lines.append(f"- **{a.total}** · {(q.question if q else a.qid)}")
            if a.suggestion:
                lines.append(f"  - {a.suggestion}")
        avg_dims: dict[str, float] = {}
        for a in session.answers:
            for k, v in a.dimensions.items():
                avg_dims.setdefault(k, 0.0)
                avg_dims[k] += v
        count = len(session.answers)
        lines += ["", "## 五维平均"]
        for k, v in sorted(avg_dims.items(), key=lambda kv: kv[1] / count):
            lines.append(f"- {k}：{round(v / count, 1)}")
        lines += ["", "## 下一步"]
        lines.append("1. 把最弱的两题重写一遍，要求每题至少出现 2 个数字")
        lines.append("2. 用手机录音，控制在 90 秒内讲完")
        lines.append("3. 让顾问随机抽一题做追问（面试官最爱追问细节和失败）")
    else:
        lines += ["", "还没有作答记录，先答 3 题再看报告。"]
    return "\n".join(lines)
