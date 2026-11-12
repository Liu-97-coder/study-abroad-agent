"""Agent 统一基类（基座任务 3.2）。

所有业务 Agent 继承它，强制获得：
- 统一入参/出参（CustomerState 进，CustomerState 出）
- 自动日志埋点 + trace_id 传播
- RAG / OCR / LLM / 安全护栏四个公共能力
- 异常兜底：任何 Agent 崩了都不许把主流程带崩，只记 errors 和风险标签
"""
from __future__ import annotations

import time
import traceback
from abc import ABC, abstractmethod

from ..schema.state_schema import CustomerState
from ..utils.text_clean import truncate
from .safety_middleware import NOTICE_TEXT


class BaseAgent(ABC):
    name: str = "base"
    stage: str | None = None

    def __init__(self, ctx):
        self.ctx = ctx

    # ---------------- 公共能力快捷方式 ----------------
    @property
    def llm(self):
        return self.ctx.llm

    @property
    def rag(self):
        return self.ctx.rag

    @property
    def ocr(self):
        return self.ctx.ocr

    @property
    def safety(self):
        return self.ctx.safety

    @property
    def storage(self):
        return self.ctx.storage

    @property
    def logger(self):
        return self.ctx.logger

    # ---------------- 生命周期 ----------------
    def run(self, state: CustomerState) -> CustomerState:
        if not state.trace_id:
            state.trace_id = self.logger.new_trace_id()
        started = time.time()
        self.logger.event(self.name, "start", trace_id=state.trace_id,
                          customer_id=state.customer_id, stage=state.stage)
        try:
            state = self._run(state)
            status = "ok"
        except Exception as exc:  # noqa: BLE001 - 兜底，绝不让单个 Agent 拖垮流程
            status = "error"
            state.errors.append(f"{self.name}: {exc}")
            self.logger.event(self.name, "error", level="ERROR", trace_id=state.trace_id,
                              customer_id=state.customer_id,
                              error=str(exc), tb=truncate(traceback.format_exc(), 600))
        finally:
            if self.name not in state.history:
                state.history.append(self.name)
            try:
                self.storage.save_customer(state)
            except Exception:  # noqa: BLE001 - 存储失败不影响返回
                pass
            self.logger.event(self.name, "finish", trace_id=state.trace_id,
                              customer_id=state.customer_id, status=status,
                              elapsed_ms=round((time.time() - started) * 1000, 1))
        return state

    @abstractmethod
    def _run(self, state: CustomerState) -> CustomerState:
        """子类实现业务逻辑。"""

    # ---------------- 工具方法 ----------------
    def llm_text(self, prompt: str, fallback: str = "", tier: str = "big",
                 customer_id: str = "system", system: str | None = None) -> str:
        return self.llm.text(prompt, fallback=fallback, tier=tier,
                             customer_id=customer_id, system=system)

    def llm_json(self, prompt: str, fallback=None, tier: str = "big",
                 customer_id: str = "system"):
        return self.llm.json(prompt, fallback=fallback, tier=tier, customer_id=customer_id)

    def search(self, collection: str, query: str, where: dict | None = None, top_k: int | None = None):
        return self.rag.search(collection, query, where=where, top_k=top_k)

    def context_text(self, chunks, max_chars: int = 4000) -> str:
        return self.rag.format_context(chunks, max_chars)

    def parse_doc(self, path=None, text=None):
        return self.ocr.parse(path=path, text=text)

    def guard_output(self, text: str, state: CustomerState) -> str:
        """任何要展示给客户/顾问的文本，出去前必须过护栏。"""
        verdict = self.safety.check(text, customer_id=state.customer_id)
        if verdict.blocked:
            self.tag(state, "违规话术已拦截", level="高", reason=verdict.reason)
            return NOTICE_TEXT
        return text

    def tag(self, state: CustomerState, risk: str, level: str = "中", reason: str = "") -> None:
        state.add_risk(risk)
        self.storage.add_risk(state.customer_id, risk, level, reason)
        self.logger.event(self.name, "risk_tag", level="WARN", trace_id=state.trace_id,
                          customer_id=state.customer_id, risk=risk, risk_level=level)

    def task(self, state: CustomerState, title: str, level: str = "普通",
             due_date: str = "", source: str | None = None) -> None:
        """加待办。同一个客户同一标题只留一条 —— 否则每次重跑都会堆一份。"""
        if any(t.get("title") == title for t in state.task_list):
            return
        state.add_task(title, level=level, due_date=due_date, source=source or self.name)
