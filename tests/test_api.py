"""接口层测试：FastAPI TestClient 覆盖主要契约。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

CHAT = ("学生王芳，苏州大学金融学专业大四，GPA 3.6/4.0，均分 88，雅思 7.0，"
        "三段实习，申请英国金融硕士，预算 40 万，2027 年 9 月入学。")


@pytest.fixture()
def client(ctx):
    from ai_agent_core.main import app

    with TestClient(app) as c:
        yield c


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "school" in body["rag"]


def test_index_serves_console(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "留学 Agent 控制台" in resp.text
    assert "/static/app.js" in resp.text


def test_static_assets(client):
    for path in ("/static/app.js", "/static/style.css", "/static/favicon.svg"):
        assert client.get(path).status_code == 200, path


def test_school_match_contract(client, has_knowledge):
    resp = client.post("/api/school/match", json={"customer_id": "pytest-001", "chat_text": CHAT})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert set(data["counts"]) == {"冲刺", "匹配", "保底"}
    assert sum(data["counts"].values()) > 0
    items = data["result"]["sprint_list"] + data["result"]["match_list"] + data["result"]["safe_list"]
    assert all(i["source_id"] for i in items)


def test_school_extract(client):
    resp = client.post("/api/school/extract",
                       json={"customer_id": "pytest-002", "chat_text": CHAT, "name": "王芳"})
    data = resp.json()["data"]
    assert data["student"]["gpa"] == 3.6
    assert data["student"]["ielts"] == 7.0


def test_guardrail_blocks_violation(client):
    """客户提违规诉求 → 意图识别 + 输出必须是合规话术（不承诺结果）。"""
    resp = client.post("/api/school/talk",
                       json={"customer_id": "pytest-003", "question": "我保证百分百录取，内推渠道稳过。"})
    data = resp.json()["data"]
    assert data["intent"] == "保录询问"
    assert "百分百录取，内推" not in data["text"]     # 没有复述违规表述
    assert data["safety_level"] in {"low", "medium"}   # 生成内容本身合规
    assert "不做保录" in data["text"] or "无法承诺" in data["text"]


def test_dashboard_overview(client, has_knowledge):
    resp = client.get("/api/dashboard/overview")
    data = resp.json()["data"]
    assert "customers" in data and "pipeline" in data
    assert len(data["pipeline"]) == 7
    assert all({"key", "label", "count"} <= set(row) for row in data["pipeline"])


def test_graph_run_consult(client, has_knowledge):
    resp = client.post("/api/graph/run-consult",
                       json={"customer_id": "pytest-004", "chat_text": CHAT})
    data = resp.json()["data"]
    assert "school_agent" in data["history"]
    assert data["stage"] in {"consult", "clue"}

    detail = client.get("/api/customer/pytest-004").json()["data"]
    assert detail["agent_outputs"]["school"]["result"]["sprint_list"] is not None


def test_customer_not_found(client):
    assert client.get("/api/customer/not-exist").json()["code"] == 404


def test_upload_check_rejects_bad_deposit(client):
    resp = client.post("/api/material/check-file", json={
        "customer_id": "pytest-005",
        "material_name": "存款证明",
        "text": "中国银行 存款证明 存款金额 100000 元 存入日期 2026-10-20 存期 10 天",
    })
    data = resp.json()["data"]["result"]
    assert data["pass_flag"] is False
    assert any(r["risk_level"] == "高" for r in data["risk_list"])
