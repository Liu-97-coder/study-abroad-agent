"""全局合规安全护栏（基座任务 4）。

三层：
1. 关键词粗筛（毫秒级，命中断言）
2. 语义复核（关键词命中后判断是"玩笑/询问"还是"正式承诺"，降误报）
3. 幻觉校验（硬性数据必须带 RAG 溯源 ID，无溯源即标记）

嵌入所有生成入口：业务 Agent 想输出给客户/顾问之前，必须过 guard()。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..config import Settings, settings as default_settings
from ..schema.common_schema import SafetyVerdict

# 留学行业硬红线词（可被 data/seed/compliance_words.json 扩充）
DEFAULT_FORBIDDEN = [
    "保录", "保过", "保底必中", "百分百录取", "100%录取", "稳录", "内推", "渠道录取",
    "不用成绩", "包过", "保签", "包签", "包录取", "保offer", "保OFFER",
]

# 出现这些词，说明更可能是"询问/假设"，不是"承诺"，降级为中风险
HEDGE_MARKERS = [
    "能不能", "可不可以", "是否", "能不能保", "假设", "如果", "万一", "听说", "有没有",
    "算不算", "吗", "?", "？", "了解一下", "问一下", "玩笑",
]

# 出现这些词，说明是在"否认/拒绝"违规承诺（例如"我们不做保录"），应判低风险
DENIAL_MARKERS = [
    "不做", "不能", "不存在", "禁止", "严禁", "无法", "不承诺", "没有", "拒绝",
    "不提供", "不保证", "不会", "不搞", "违规",
]

NOTICE_TEXT = (
    "【合规预警】检测到疑似违规承诺话术。按机构风控规则：不得承诺保录/保过/内推/百分百录取，"
    "院校录取由学校独立审核决定。请改为客观陈述录取要求与学生现状差距，并记录已告知风险。"
)


class SafetyGuard:
    def __init__(self, cfg: Settings | None = None, llm=None, logger=None,
                 extra_words: list[str] | None = None):
        self.cfg = cfg or default_settings
        self.llm = llm
        self.logger = logger
        self.forbidden = list(DEFAULT_FORBIDDEN)
        self._load_seed_words()
        if extra_words:
            self.forbidden.extend(extra_words)
        self.forbidden = sorted(set(self.forbidden), key=len, reverse=True)
        self._pattern = re.compile("|".join(re.escape(w) for w in self.forbidden), re.I)

    def _load_seed_words(self) -> None:
        path = Path(self.cfg.seed_dir) / "compliance_words.json"
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            words = data.get("forbidden_words", [])
            if isinstance(words, list):
                self.forbidden.extend(str(w) for w in words if w)
        except (OSError, json.JSONDecodeError):
            pass

    # ---------------- 第一层：关键词 ----------------
    def keyword_scan(self, text: str) -> list[str]:
        if not text:
            return []
        return sorted({m.group(0) for m in self._pattern.finditer(text)})

    @staticmethod
    def _local_level(text: str, hits: list[str]) -> str:
        """看违规词附近的语气：疑问/假设 → 中；否认 → 低；其余 → 高。

        注意顺序：先判疑问再判否认，否则"能不能保录"会因为含"不能"被判成否认。
        """
        for hit in hits:
            idx = text.find(hit)
            window = text[max(0, idx - 14): idx + len(hit) + 14]
            if any(marker in window for marker in HEDGE_MARKERS):
                return "medium"
            if any(marker in window for marker in DENIAL_MARKERS):
                return "low"
        return "high"

    # ---------------- 第二层：语义复核 ----------------
    def _semantic_review(self, text: str, hits: list[str]) -> str | None:
        """返回 None 表示无法判断（沿用规则结论），否则返回 low/medium/high。"""
        if not self.llm or not getattr(self.llm, "available", False):
            return None
        prompt = (
            "判断下面这段留学顾问话术是【正式承诺】还是【询问/假设/玩笑】。\n"
            f"命中违规词：{hits}\n文本：{text[:800]}\n"
            '只输出 JSON：{"level":"low|medium|high","reason":"一句话"}'
        )
        data = self.llm.json(prompt, fallback=None, tier="small")
        if isinstance(data, dict) and data.get("level") in {"low", "medium", "high"}:
            return str(data["level"])
        return None

    # ---------------- 对外主入口 ----------------
    def check(self, text: str, use_llm: bool = True, customer_id: str = "") -> SafetyVerdict:
        hits = self.keyword_scan(text or "")
        if not hits:
            return SafetyVerdict(level="low", blocked=False, sanitized_text=text or "")

        level = self._local_level(text or "", hits)
        reason = f"命中违规词：{'、'.join(hits)}"
        if use_llm:
            semantic = self._semantic_review(text or "", hits)
            if semantic:
                level = semantic
                reason += f"（语义复核：{semantic}）"

        blocked = level == "high" and self.cfg.safety_strict
        verdict = SafetyVerdict(level=level, blocked=blocked, hits=hits, reason=reason,
                                sanitized_text=self.sanitize(text or "") if blocked else (text or ""))

        if self.logger and level != "low":
            self.logger.event("safety", "forbidden_hit", level="WARN",
                              customer_id=customer_id, hits=hits, verdict=level, blocked=blocked)
        return verdict

    def sanitize(self, text: str) -> str:
        return self._pattern.sub("【已拦截违规表述】", text or "")

    def guard(self, text: str, customer_id: str = "", use_llm: bool = True) -> str:
        """要输出给客户/顾问的文本走这里：高危直接换成合规提示，不留原文。"""
        verdict = self.check(text, use_llm=use_llm, customer_id=customer_id)
        if verdict.blocked:
            return NOTICE_TEXT
        return text

    # ---------------- 第三层：幻觉校验 ----------------
    def verify_citations(self, items: list[dict], source_field: str = "source_id") -> list[int]:
        """硬性数据（GPA 门槛/截止日期/存期）必须带溯源，返回缺失溯源的行号。"""
        missing = []
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            if not item.get(source_field):
                missing.append(idx)
        return missing

    def risk_level_of(self, items: list[dict]) -> str:
        missing = self.verify_citations(items)
        if not missing:
            return "low"
        return "high" if len(missing) >= max(1, len(items) // 2) else "medium"
