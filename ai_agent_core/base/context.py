"""依赖装配：把基座四个能力 + 存储装进一个上下文，Agent 只认这个对象。

单例由 get_context() 提供，避免每次请求重复创建 LLM 客户端/加载向量索引。
"""
from __future__ import annotations

from dataclasses import dataclass

from ..config import Settings, settings as default_settings
from ..storage import Storage
from .llm_dispatch import LLMDispatcher
from .logger_trace import TraceLogger
from .ocr_client import OCRClient
from .rag_client import RAGClient
from .safety_middleware import SafetyGuard


@dataclass
class AgentContext:
    settings: Settings
    logger: TraceLogger
    llm: LLMDispatcher
    rag: RAGClient
    ocr: OCRClient
    safety: SafetyGuard
    storage: Storage

    @classmethod
    def build(cls, cfg: Settings | None = None) -> "AgentContext":
        cfg = cfg or default_settings
        logger = TraceLogger(cfg.log_dir)
        llm = LLMDispatcher(cfg, logger=logger)
        rag = RAGClient(cfg, llm=llm, logger=logger)
        ocr = OCRClient(cfg, llm=llm, logger=logger)
        safety = SafetyGuard(cfg, llm=llm, logger=logger)
        storage = Storage(cfg.runtime_dir / "crm.db")
        return cls(settings=cfg, logger=logger, llm=llm, rag=rag, ocr=ocr,
                   safety=safety, storage=storage)


_CONTEXT: AgentContext | None = None


def get_context(cfg: Settings | None = None) -> AgentContext:
    global _CONTEXT
    if _CONTEXT is None:
        _CONTEXT = AgentContext.build(cfg)
    return _CONTEXT


def reset_context() -> None:
    global _CONTEXT
    _CONTEXT = None
