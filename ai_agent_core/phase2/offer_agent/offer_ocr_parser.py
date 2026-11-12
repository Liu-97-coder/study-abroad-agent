"""Cond Offer 专用 OCR 解析（Offer Agent 步骤 1）。

Offer 里最要命的是"条件藏在长英文句子里"：
"subject to achieving an overall average of 85% and IELTS 7.0 with no band below 6.5"
正则先抓结构（均分/语言/押金/截止），LLM 再补长句理解。
"""
from __future__ import annotations

import re

from ...prompt.offer_cond_prompt import OCR_OFFER_COND_PROMPT
from ...schema.offer_schema import CondCondition
from ...utils.date_utils import fmt_date, parse_date

COND_PATTERNS = {
    "均分": [r"(?:average|均分|overall score|final average)[^\d\n]{0,20}(\d{2,3}(?:\.\d+)?)\s*%?",
             r"(?:at least|不低于)\s*(\d{2,3})\s*%"],
    "语言": [r"(?:IELTS|雅思)[^\d\n]{0,15}(\d(?:\.\d)?)(?:\s*(?:with no band below|单项不低于)\s*(\d(?:\.\d)?))?",
             r"(?:TOEFL|托福)[^\d\n]{0,15}(\d{2,3})"],
    "GRE": [r"(?:GRE)[^\d\n]{0,10}(\d{3})"],
    "毕业证": [r"((?:degree certificate|毕业证|学位证)[^.\n]{0,30})"],
}

PAYMENT_PATTERN = re.compile(
    r"(?:deposit|押金|留位费)[^\d\n]{0,15}([0-9][0-9,]*(?:\.\d{2})?)\s*(GBP|£|USD|\$|RMB|CNY|元)?", re.I)
CONDITIONAL_HINTS = ["conditional", "subject to", "provided that", "有条件", "con offer"]


def is_conditional(raw: str) -> bool:
    low = (raw or "").lower()
    return any(h in low for h in CONDITIONAL_HINTS)


def extract_conditions(raw: str) -> list[CondCondition]:
    raw = raw or ""
    conditions: list[CondCondition] = []
    for cond_type, patterns in COND_PATTERNS.items():
        for pattern in patterns:
            m = re.search(pattern, raw, re.I)
            if not m:
                continue
            value = m.group(1)
            if cond_type == "均分":
                require = f"均分 {value}%"
            elif cond_type == "语言":
                require = f"IELTS {value}" if "IELTS" in pattern or "雅思" in pattern else f"TOEFL {value}"
                if m.lastindex and m.lastindex >= 2 and m.group(2):
                    require += f"（单项不低于 {m.group(2)}）"
            elif cond_type == "GRE":
                require = f"GRE {value}"
            else:
                require = "需提交毕业证/学位证"
            conditions.append(CondCondition(cond_type=cond_type, require_value=require))
            break
    if not conditions:
        conditions.append(CondCondition(cond_type="其他", require_value="未识别出明确条件，需人工复核 Offer 原文"))
    return conditions


def extract_payment(raw: str) -> dict:
    m = PAYMENT_PATTERN.search(raw or "")
    if not m:
        return {}
    return {"amount": m.group(1).replace(",", ""), "currency": (m.group(2) or "").strip()}


def extract_school_info(raw: str) -> dict:
    info = {}
    text = raw or ""
    m = re.search(r"((?:The\s+)?University of\s+[A-Z][A-Za-z]+"
                  r"(?:\s+(?!Programme|Program|Course|September|January|Conditional|Offer)"
                  r"[A-Z][A-Za-z]+)*)", text)
    if m:
        info["school_name"] = re.sub(r"\s+", " ", m.group(1)).strip()
    m = re.search(r"(?:Programme|Program|Course|专业)[:：\s]{0,3}([A-Za-z][A-Za-z\s&]{3,60})", text)
    if m:
        info["major"] = re.sub(r"\s+", " ", m.group(1)).strip().split("\n")[0]
    m = re.search(r"(?:September|Jan(?:uary)?|Fall|Autumn)\s*(20\d{2})", text, re.I)
    if m:
        info["intake"] = m.group(0)
    m = re.search(r"(?:accept|respond|reply|截止)[^\d\n]{0,20}(\d{1,2}\s+\w+\s+20\d{2}|\d{4}-\d{2}-\d{2})",
                  text, re.I)
    if m:
        info["deadline"] = fmt_date(parse_date(m.group(1)))
    return info


def parse_offer(raw_text: str, ctx=None, customer_id: str = "system") -> dict:
    info = extract_school_info(raw_text)
    conditions = extract_conditions(raw_text)
    payment = extract_payment(raw_text)

    if ctx is not None and ctx.llm.available:
        data = ctx.llm.json(OCR_OFFER_COND_PROMPT.format(raw_text=raw_text[:4000]),
                            fallback=None, tier="big", customer_id=customer_id)
        if isinstance(data, dict):
            info.update({k: v for k, v in data.items() if k in ("school_name", "major", "intake")})
            for cond in data.get("conditions") or []:
                if isinstance(cond, dict) and cond.get("cond_type"):
                    conditions.append(CondCondition(cond_type=str(cond["cond_type"]),
                                                    require_value=str(cond.get("require_value", ""))))
            if "is_conditional" in data:
                info["is_conditional"] = bool(data["is_conditional"])

    info.setdefault("is_conditional", is_conditional(raw_text))
    return {"info": info, "conditions": conditions, "payment": payment,
            "raw_text": (raw_text or "")[:6000]}
