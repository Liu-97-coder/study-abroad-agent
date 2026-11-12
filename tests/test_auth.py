"""鉴权单测：密码哈希、Token 签发/校验，以及"顾问只能看自己客户"的接口级隔离。"""
from __future__ import annotations

import dataclasses
import shutil
import time

import pytest
from fastapi.testclient import TestClient

from ai_agent_core.auth import User, create_token, decode_token, hash_password, verify_password


class TestPassword:
    def test_hash_and_verify(self):
        stored = hash_password("admin123")
        assert stored.startswith("pbkdf2_sha256$")
        assert verify_password("admin123", stored)
        assert not verify_password("wrong", stored)

    def test_same_password_different_salt(self):
        assert hash_password("x") != hash_password("x")

    def test_broken_hash_rejected(self):
        assert not verify_password("x", "not-a-hash")


class TestToken:
    def test_roundtrip(self):
        user = User("advisor1", "advisor", "顾问·李")
        token = create_token(user, "secret", ttl=60)
        decoded = decode_token(token, "secret")
        assert decoded and decoded.username == "advisor1"
        assert decoded.role == "advisor"

    def test_wrong_secret(self):
        token = create_token(User("a"), "secret", ttl=60)
        assert decode_token(token, "another-secret") is None

    def test_expired(self):
        token = create_token(User("a"), "secret", ttl=-1)
        assert decode_token(token, "secret") is None

    def test_tampered_payload(self):
        token = create_token(User("a"), "secret", ttl=60)
        head, payload, sig = token.split(".")
        forged = ".".join([head, payload[:-2] + ("AA" if payload[-2:] != "AA" else "BB"), sig])
        assert decode_token(forged, "secret") is None

    def test_garbage(self):
        assert decode_token("", "secret") is None
        assert decode_token("a.b", "secret") is None


@pytest.fixture()
def auth_client(tmp_path):
    """单独一套开启鉴权的 Context（和默认测试用的关闭鉴权 Context 隔离）。"""
    import ai_agent_core.base.context as ctx_module

    previous = ctx_module._CONTEXT
    cfg = dataclasses.replace(previous.settings, runtime_dir=tmp_path, log_dir=tmp_path,
                              auth_enabled=True, auth_secret="test-secret")
    context = ctx_module.AgentContext.build(cfg)
    context.storage.ensure_default_users("admin", "admin123", extras=[
        ("advisor1", "123456", "advisor", "顾问·李"),
        ("advisor2", "123456", "advisor", "顾问·王"),
    ])
    ctx_module._CONTEXT = context

    from ai_agent_core.main import app

    with TestClient(app) as client:
        yield client
    ctx_module._CONTEXT = previous


def _login(client, username, password):
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["token"]


def test_login_rejects_wrong_password(auth_client):
    resp = auth_client.post("/api/auth/login", json={"username": "admin", "password": "bad"})
    assert resp.status_code == 401


def test_protected_api_requires_token(auth_client):
    assert auth_client.get("/api/customer/list").status_code == 401
    assert auth_client.post("/api/school/match", json={"customer_id": "x"}).status_code == 401


def test_public_endpoints_open(auth_client):
    assert auth_client.get("/health").status_code == 200
    assert auth_client.get("/api/dashboard/health").status_code == 200
    assert auth_client.get("/").status_code == 200


def test_me_returns_profile(auth_client):
    token = _login(auth_client, "admin", "admin123")
    resp = auth_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.json()["data"]["role"] == "admin"


def test_advisor_only_sees_own_customers(auth_client):
    import ai_agent_core.base.context as ctx_module
    from ai_agent_core.schema.state_schema import CustomerState

    context = ctx_module._CONTEXT
    context.storage.save_customer(CustomerState(customer_id="c-a1", customer_name="李客户",
                                                owner="advisor1", stage="consult"))
    context.storage.save_customer(CustomerState(customer_id="c-a2", customer_name="王客户",
                                                owner="advisor2", stage="consult"))

    token = _login(auth_client, "advisor1", "123456")
    headers = {"Authorization": f"Bearer {token}"}

    rows = auth_client.get("/api/customer/list", headers=headers).json()["data"]
    assert {r["customer_id"] for r in rows} == {"c-a1"}

    assert auth_client.get("/api/customer/c-a1", headers=headers).status_code == 200
    assert auth_client.get("/api/customer/c-a2", headers=headers).status_code == 403

    admin = _login(auth_client, "admin", "admin123")
    admin_rows = auth_client.get("/api/customer/list",
                                 headers={"Authorization": f"Bearer {admin}"}).json()["data"]
    assert len(admin_rows) >= 2


def test_admin_can_create_user(auth_client):
    token = _login(auth_client, "admin", "admin123")
    headers = {"Authorization": f"Bearer {token}"}
    body = {"username": "advisor9", "password": "pw123456", "role": "advisor", "display_name": "新顾问"}
    assert auth_client.post("/api/auth/users", json=body, headers=headers).json()["code"] == 0
    assert auth_client.post("/api/auth/users", json=body, headers=headers).json()["code"] == 400
    assert _login(auth_client, "advisor9", "pw123456")


def test_advisor_cannot_create_user(auth_client):
    token = _login(auth_client, "advisor1", "123456")
    resp = auth_client.post("/api/auth/users",
                            json={"username": "x", "password": "y"},
                            headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
