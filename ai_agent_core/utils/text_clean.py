"""文本清洗、分词、关键词覆盖度。中文用字二元组，英文用词。"""
from __future__ import annotations

import re
from collections import Counter

_WS = re.compile(r"[ \t\u3000]+")
_CJK = re.compile(r"[\u4e00-\u9fa5]")
_WORD = re.compile(r"[a-zA-Z]{2,}")

STOPWORDS = set("的 了 和 是 在 我 有 就 不 人 都 一 一个 上 也 很 到 说 要 去 你 会 着 没有 看 好 自己 这 那 就 与 及 或 等".split())


def clean(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = _WS.sub(" ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def strip_markdown(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text or "", flags=re.S)
    text = re.sub(r"[#>*`_\-]{1,}", " ", text)
    return clean(text)


def tokenize(text: str) -> list[str]:
    text = (text or "").lower()
    tokens = _WORD.findall(text)
    chars = _CJK.findall(text)
    tokens += ["".join(chars[i:i + 2]) for i in range(len(chars) - 1)]
    return [t for t in tokens if t not in STOPWORDS]


def term_freq(text: str) -> Counter:
    return Counter(tokenize(text))


def keyword_coverage(keywords: list[str], text: str) -> float:
    """keywords 在 text 中的覆盖率 0-1，用于"专业匹配度""经历真实度"这类可解释指标。"""
    if not keywords:
        return 0.0
    t = (text or "").lower()
    hit = sum(1 for k in keywords if k and k.lower() in t)
    return round(hit / len(keywords), 3)


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"[。！？!?；;\n]+", text or "")
    return [p.strip() for p in parts if p.strip()]


def ngrams(text: str, n: int = 3) -> set[str]:
    t = re.sub(r"\s+", "", (text or "").lower())
    return {t[i:i + n] for i in range(max(0, len(t) - n + 1))}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return round(len(a & b) / len(a | b), 3)


def truncate(text: str, limit: int = 400) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit] + "…"
