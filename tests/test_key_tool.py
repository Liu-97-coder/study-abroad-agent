"""Key 配置工具的单元测试：打码、写入不破坏原文件、备份回滚。"""
from __future__ import annotations

import importlib

import pytest


@pytest.fixture()
def tool(tmp_path, monkeypatch):
    mod = importlib.import_module("scripts.set_llm_key")
    mod = importlib.reload(mod)
    env = tmp_path / ".env"
    env.write_text("# 注释要保留\nLLM_PROVIDER=mock\nAUTH_ENABLED=1\n", encoding="utf-8")
    monkeypatch.setattr(mod, "ENV_FILE", env)
    monkeypatch.setattr(mod, "BACKUP", tmp_path / ".env.bak")
    return mod


def test_mask_hides_key():
    mod = importlib.import_module("scripts.set_llm_key")
    assert "sk-12345" not in mod.mask("sk-1234567890abcdef")
    assert mod.mask("") == "(空)"
    assert "***" in mod.mask("short")


def test_write_env_updates_and_keeps_comments(tool):
    tool.write_env({"LLM_PROVIDER": "deepseek", "LLM_API_KEY": "sk-test"})
    text = tool.ENV_FILE.read_text(encoding="utf-8")
    assert "LLM_PROVIDER=deepseek" in text
    assert "LLM_API_KEY=sk-test" in text
    assert "# 注释要保留" in text
    assert "AUTH_ENABLED=1" in text


def test_read_env_roundtrip(tool):
    tool.write_env({"LLM_MODEL_BIG": "deepseek-chat"})
    env = tool.read_env()
    assert env["LLM_MODEL_BIG"] == "deepseek-chat"
    assert env["AUTH_ENABLED"] == "1"


def test_restore_brings_back_old_file(tool):
    tool.BACKUP.write_text("LLM_PROVIDER=mock\n", encoding="utf-8")
    assert tool.restore() == 0
    assert "LLM_PROVIDER=mock" in tool.ENV_FILE.read_text(encoding="utf-8")


def test_restore_without_backup_is_safe(tool):
    assert tool.restore() == 1
