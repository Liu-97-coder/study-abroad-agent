"""pytest 公共夹具：把运行目录指向临时目录，不污染你的演示数据。"""
from __future__ import annotations

import dataclasses
import shutil
from pathlib import Path

import pytest

from ai_agent_core.base.context import AgentContext
from ai_agent_core.config import settings


@pytest.fixture(scope="session")
def ctx(tmp_path_factory):
    """独立 Context：复制一份知识库索引到临时目录，客户中台也用临时文件。"""
    tmp = tmp_path_factory.mktemp("runtime")
    rag_dir = tmp / "rag"
    rag_dir.mkdir()
    for src in Path(settings.runtime_dir, "rag").glob("*.json"):
        shutil.copy(src, rag_dir / src.name)

    # 测试一律走 mock：不花钱、不依赖网络、结果可复现
    cfg = dataclasses.replace(settings, runtime_dir=tmp, log_dir=tmp,
                              auth_enabled=False, llm_provider="mock", llm_api_key="")
    context = AgentContext.build(cfg)

    import ai_agent_core.base.context as ctx_module

    ctx_module._CONTEXT = context
    yield context
    ctx_module._CONTEXT = None


@pytest.fixture()
def has_knowledge(ctx):
    if sum(ctx.rag.stats().values()) == 0:
        pytest.skip("知识库为空，先运行 scripts/ingest_seed.py")
