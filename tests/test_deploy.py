"""部署资产测试：Dockerfile / compose / 健康检查脚本本身是否自洽。

不启动容器（本机可能没有 Docker），只保证"文件引用正确、脚本逻辑正确"。
真正的构建等价验证见 scripts/check_deploy.py。
"""
from __future__ import annotations

import io
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_essentials():
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "FROM python:3.12-slim" in text
    assert "pip install" in text and "requirements.txt" in text
    assert "HEALTHCHECK" in text and "scripts/healthcheck.py" in text
    assert "--host 0.0.0.0" in text
    assert "USER appuser" in text, "应该用非 root 运行"
    assert "PYTHONIOENCODING=utf-8" in text


def test_dockerfile_copies_existing_paths():
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    for path in re.findall(r"^COPY\s+(\S+)", text, re.M):
        if path.startswith("--"):
            continue
        assert (ROOT / path).exists(), f"Dockerfile COPY 了不存在的路径：{path}"


def test_compose_config():
    yaml = pytest.importorskip("yaml", reason="可选依赖：pip install pyyaml 才校验 compose")
    data = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    service = data["services"]["agent"]
    assert "build" in service
    assert any("8000" in str(p) for p in service["ports"])
    assert "./runtime:/app/runtime" in service["volumes"]
    assert service["healthcheck"]["test"][0] == "CMD"
    assert "AUTH_SECRET" in service["environment"]


def test_dockerignore_covers_heavy_dirs():
    text = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    for pattern in (".venv/", "runtime/", "logs/", "__pycache__/"):
        assert pattern in text, f".dockerignore 应排除 {pattern}"


def test_requirements_declare_runtime_essentials():
    text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    for pkg in ("fastapi", "uvicorn", "pydantic", "langgraph", "python-multipart"):
        assert pkg in text, f"requirements.txt 缺 {pkg}"


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_healthcheck_script_ok(monkeypatch, capsys):
    import scripts.healthcheck as hc

    payload = json.dumps({"status": "ok", "rag": {"school": 33, "visa": 4}}).encode()
    monkeypatch.setattr(hc.urllib.request, "urlopen", lambda *a, **k: _FakeResponse(payload))
    assert hc.main() == 0
    assert "healthy" in capsys.readouterr().out


def test_healthcheck_fails_on_empty_knowledge(monkeypatch):
    import scripts.healthcheck as hc

    payload = json.dumps({"status": "ok", "rag": {"school": 0}}).encode()
    monkeypatch.setattr(hc.urllib.request, "urlopen", lambda *a, **k: _FakeResponse(payload))
    assert hc.main() == 1


def test_healthcheck_fails_when_unreachable(monkeypatch):
    import scripts.healthcheck as hc

    def boom(*args, **kwargs):
        raise hc.urllib.error.URLError("connection refused")

    monkeypatch.setattr(hc.urllib.request, "urlopen", boom)
    assert hc.main() == 1


def test_deploy_doc_exists():
    doc = ROOT / "docs" / "部署.md"
    assert doc.exists()
    text = doc.read_text(encoding="utf-8")
    assert "systemd" in text and "nginx" in text and "AUTH_SECRET" in text
