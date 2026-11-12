"""LLM 输出 JSON 的容错解析。模型爱加 ```json 围栏，必须兜住。"""
from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def loads_lenient(text: str | None, default: Any = None) -> Any:
    if not text:
        return default
    text = text.strip()
    m = _FENCE.search(text)
    if m:
        text = m.group(1).strip()
    for candidate in (text, _extract_json_span(text)):
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return default


def _extract_json_span(text: str) -> str | None:
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = text.find(opener), text.rfind(closer)
        if start != -1 and end > start:
            return text[start:end + 1]
    return None


def dumps_zh(data: Any, indent: int = 2) -> str:
    return json.dumps(data, ensure_ascii=False, indent=indent, default=str)
