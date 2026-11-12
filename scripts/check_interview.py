"""面试模拟自检：出题 → 评分 → 复盘 → 图里能被路由唤醒。

用法：
    python scripts/check_interview.py --base http://127.0.0.1:8000
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

TOKEN: dict[str, str | None] = {"value": None}

GOOD = ("当时我在银行实习，负责风控规则测试。我的任务是把上线前的漏测补上。"
        "我先梳理 3 个核心场景，写了 120 条测试用例，用 Python 做批量回归，"
        "最后发现 8 个规则漏洞，覆盖 3 个高风险场景，上线后零事故。")
WEAK = "嗯，就是做了些事情，反正还行吧。"


def call(base: str, path: str, payload: dict | None = None):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload else None
    headers = {"Content-Type": "application/json"}
    if TOKEN["value"]:
        headers["Authorization"] = f"Bearer {TOKEN['value']}"
    req = urllib.request.Request(base.rstrip("/") + path, data=data,
                                 method="POST" if data else "GET", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            return exc.code, {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--customer", default="demo-001")
    args = parser.parse_args()
    base = args.base

    results: list[tuple[str, bool]] = []

    def check(name, ok, detail=""):
        results.append((name, ok))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}  {detail}")

    status, body = call(base, "/api/auth/login", {"username": "admin", "password": "admin123"})
    TOKEN["value"] = (body.get("data") or {}).get("token")
    check("登录", bool(TOKEN["value"]))

    print("\n① 出题（按目标专业抽题）")
    status, body = call(base, "/api/interview/start", {"customer_id": args.customer, "count": 6})
    data = body.get("data") or {}
    questions = data.get("questions") or []
    check("生成 6 道题", len(questions) == 6, f"target={data.get('target')}")
    cats = [q["category"] for q in questions]
    print(f"     题序：{cats}")
    check("题型有梯度", len(set(cats)) >= 4, f"{len(set(cats))} 类")
    session_id = data.get("session_id", "")

    print("\n② 评分（好答案 vs 敷衍答案）")
    qid = questions[0]["qid"]
    _, body = call(base, "/api/interview/answer",
                   {"session_id": session_id, "qid": qid, "answer": GOOD})
    good = (body.get("data") or {}).get("score", {})
    check("好答案得分 > 60", good.get("total", 0) > 60,
          f"{good.get('total')} 分 | 维度 {good.get('dimensions')}")

    _, body2 = call(base, "/api/interview/answer",
                    {"session_id": session_id, "qid": qid, "answer": WEAK})
    weak = (body2.get("data") or {}).get("score", {})
    check("敷衍答案得分更低", weak.get("total", 100) < good.get("total", 0),
          f"{weak.get('total')} 分")
    check("给了整改建议", bool(weak.get("suggestion")), (weak.get("suggestion") or "")[:40])

    print("\n③ 复盘报告")
    _, body = call(base, f"/api/interview/report?session_id={session_id}")
    report = (body.get("data") or {}).get("report", "")
    check("报告含平均分与改进项", "平均分" in report and "下一步" in report, f"{len(report)} 字")

    print("\n④ 图调度：被标记时才会插入面试 Agent")
    _, body = call(base, "/api/graph/run-application-flow",
                   {"customer_id": "iv-graph", "payload": {"interview_requested": True},
                    "chat_text": "学生测试，计算机专业，GPA 3.2，雅思 6.5，申请英国计算机硕士。"})
    history = (body.get("data") or {}).get("history") or []
    check("执行链包含 interview_agent", "interview_agent" in history, f"{history}")

    failed = [r for r in results if not r[1]]
    print(f"\n{'全部通过 ✅' if not failed else f'{len(failed)} 项未通过 ❌'}")
    print(f"\n控制台里打开客户 → 「面试」Tab → 生成模拟面试即可体验。")
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
