"""院校邮件意图识别与关键信息抽取（网申 Agent 步骤 2）。

五类意图：补件通知 / 面试邀请 / 押金提醒 / Offer 发放 / 拒信WL
规则先判（关键词），LLM 复核补字段 —— 邮件误判的代价是漏掉补件截止，非常大。
"""
from __future__ import annotations

import re

from ...prompt.email_parse_prompt import MAIL_INTENT_PARSE_PROMPT
from ...schema.application_schema import MailInfo
from ...utils.date_utils import fmt_date, parse_date

INTENT_KEYWORDS = {
    "补件通知": ["additional document", "supplement", "missing document", "further information",
                 "补充材料", "补件", "outstanding"],
    "面试邀请": ["interview", "面试", "kira", "video assessment", "zoom meeting"],
    "押金提醒": ["deposit", "tuition deposit", "押金", "留位费", "payment deadline"],
    "Offer发放": ["offer", "congratulations", "pleased to inform", "录取"],
    "拒信WL": ["regret", "unsuccessful", "waiting list", "not able to offer", "拒信", "候补"],
}

MATERIAL_HINTS = ["成绩单", "transcript", "护照", "passport", "存款", "bank statement",
                  "推荐信", "reference", "毕业证", "degree certificate", "语言", "ielts", "toefl",
                  "writing sample", "cv", "resume", "作品集", "portfolio"]


def detect_intent(text: str) -> str:
    low = (text or "").lower()
    best, score = "其他", 0
    for intent, words in INTENT_KEYWORDS.items():
        hits = sum(1 for w in words if w.lower() in low)
        if hits > score:
            best, score = intent, hits
    return best


def extract_by_rules(text: str) -> MailInfo:
    intent = detect_intent(text)
    deadline = None
    m = re.search(r"(?:deadline|截止|before|by)\D{0,12}"
                  r"(\d{1,2}\s*(?:st|nd|rd|th)?\s+[A-Za-z]+\s+\d{4}|\d{4}[-/.]\d{1,2}[-/.]\d{1,2})",
                  text or "", re.I)
    if m:
        deadline = fmt_date(parse_date(m.group(1))) or None

    supplements = [hint for hint in MATERIAL_HINTS if hint.lower() in (text or "").lower()]
    deposit = None
    m = re.search(r"(?:deposit|押金|留位费)[^\d]{0,10}([0-9][0-9,]*)\s*(GBP|£|USD|\$|RMB|元)?",
                  text or "", re.I)
    if m:
        deposit = f"{m.group(1)} {m.group(2) or ''}".strip()

    return MailInfo(mail_intent=intent, deadline=deadline, need_supplement=supplements[:6],
                    extra_notice=f"押金：{deposit}" if deposit else "",
                    confidence=0.85 if intent != "其他" else 0.4)


def parse_email(subject: str, text: str, ctx=None, customer_id: str = "system") -> MailInfo:
    content = f"Subject: {subject}\n{text}"
    info = extract_by_rules(content)
    info.source_subject = subject

    if ctx is not None and ctx.llm.available:
        data = ctx.llm.json(MAIL_INTENT_PARSE_PROMPT.format(mail_text=content[:3000]),
                            fallback=None, tier="small", customer_id=customer_id)
        if isinstance(data, dict):
            info.mail_intent = data.get("mail_intent", info.mail_intent)
            info.deadline = data.get("deadline") or info.deadline
            if isinstance(data.get("need_supplement"), list):
                info.need_supplement = [str(x) for x in data["need_supplement"]][:8]
            info.extra_notice = data.get("extra_notice", info.extra_notice)
            info.confidence = float(data.get("confidence", info.confidence) or info.confidence)
    return info
