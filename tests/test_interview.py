"""面试模拟：题库 / 评分 / 接口。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ai_agent_core.phase2.interview_agent.answer_scorer import build_report, score_answer
from ai_agent_core.phase2.interview_agent.question_bank import load_bank, pick_from_bank
from ai_agent_core.schema.interview_schema import InterviewSession
from ai_agent_core.schema.student_schema import StudentBasicInfo

GOOD = ("当时我在银行实习，负责风控规则测试（背景）。我的任务是把上线前的规则漏测补上。"
        "我先梳理了 3 个核心场景，写了 120 条测试用例，用 Python 做批量回归，"
        "最后发现 8 个规则漏洞，覆盖了 3 个高风险场景，上线后零事故（结果）。")
WEAK = "嗯，就是做了些事情，反正还行吧。"


def test_bank_loaded():
    bank = load_bank()
    assert len(bank) >= 15
    assert all(q.qid and q.question for q in bank)
    assert {q.category for q in bank} >= {"动机", "学术", "行为", "思辨"}


def test_pick_respects_count_and_diversity():
    student = StudentBasicInfo(target_major="计算机", target_country=["英国"], target_degree="硕士")
    picked = pick_from_bank(student, count=6)
    assert len(picked) == 6
    assert len({q.qid for q in picked}) == 6
    categories = {q.category for q in picked}
    assert "动机" in categories
    assert len(categories) >= 4
    # 专业题应优先匹配计算机
    assert any(q.major in {"计算机", "通用"} for q in picked)


def test_pick_falls_back_when_major_unknown():
    student = StudentBasicInfo(target_major="考古学", target_country=["冰岛"])
    picked = pick_from_bank(student, count=5)
    assert len(picked) == 5


class TestScoring:
    def test_empty_answer_scores_zero(self):
        q = load_bank()[0]
        score = score_answer(q, "")
        assert score.total == 0
        assert "没有作答" in "".join(score.feedback)

    def test_good_beats_weak(self):
        q = next(x for x in load_bank() if x.category == "行为")
        good = score_answer(q, GOOD)
        weak = score_answer(q, WEAK)
        assert good.total > weak.total
        assert set(good.dimensions) == {"结构", "具体性", "量化", "专业匹配", "表达"}

    def test_quant_dimension_reacts_to_numbers(self):
        q = load_bank()[0]
        with_numbers = score_answer(q, GOOD)
        without = score_answer(q, GOOD.replace("120 条", "很多").replace("8 个", "几个")
                               .replace("3 个", "一些"))
        assert with_numbers.dimensions["量化"] > without.dimensions["量化"]

    def test_suggestion_present(self):
        q = load_bank()[0]
        assert score_answer(q, WEAK).suggestion


def test_report_contains_summary():
    q = load_bank()[0]
    session = InterviewSession(session_id="iv-test", target="英国·硕士·计算机",
                               questions=[q], answers=[score_answer(q, GOOD)])
    session.avg_score = session.answers[0].total
    text = build_report(session)
    assert "模拟面试复盘" in text
    assert "平均分" in text
    assert "五维平均" in text


@pytest.fixture()
def client(ctx):
    from ai_agent_core.main import app

    with TestClient(app) as c:
        yield c


def test_api_flow(client):
    start = client.post("/api/interview/start",
                        json={"customer_id": "iv-cust", "count": 4})
    data = start.json()["data"]
    assert len(data["questions"]) == 4
    session_id = data["session_id"]

    qid = data["questions"][0]["qid"]
    resp = client.post("/api/interview/answer",
                       json={"session_id": session_id, "qid": qid, "answer": GOOD})
    body = resp.json()["data"]
    assert body["score"]["total"] > 0
    assert body["answered"] == 1

    report = client.get(f"/api/interview/report?session_id={session_id}").json()["data"]
    assert report["answered"] == 1
    assert "复盘" in report["report"]

    sessions = client.get("/api/interview/sessions?customer_id=iv-cust").json()["data"]
    assert any(s["session_id"] == session_id for s in sessions)


def test_api_rejects_unknown_session(client):
    assert client.post("/api/interview/answer",
                       json={"session_id": "nope", "qid": "x", "answer": "abc"}).json()["code"] == 404
