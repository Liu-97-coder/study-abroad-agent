"""离职交接打包（三期模块 C）。

一个顾问离职，系统把名下客户分成四类打包：
紧急待办 / 风险客户 / 普通在途 / 待签约。
每份客户附 AI 生成内容溯源链接，新人可追到每一版文书的来源。
"""
from __future__ import annotations

CATEGORIES = ["紧急待办", "风险客户", "普通在途", "待签约"]


def classify(state) -> str:
    if state.stage in {"clue", "consult"}:
        return "待签约"
    urgent = [t for t in state.task_list if t.get("level") == "紧急"]
    if urgent:
        return "紧急待办"
    if state.risk_tags:
        return "风险客户"
    return "普通在途"


def build_handover(advisor: str, states: list, storage=None) -> dict:
    buckets = {name: [] for name in CATEGORIES}
    for state in states:
        category = classify(state)
        versions = storage.list_versions(state.customer_id) if storage else []
        buckets[category].append({
            "customer_id": state.customer_id,
            "name": state.customer_name or "",
            "stage": state.stage,
            "risk_tags": state.risk_tags,
            "open_tasks": [t["title"] for t in state.task_list if t.get("status") == "open"][:5],
            "doc_versions": versions[:5],
            "last_outputs": list(state.agent_outputs.keys()),
        })

    lines = [f"# 客户交接清单 · 顾问 {advisor}", ""]
    for name in CATEGORIES:
        rows = buckets[name]
        lines.append(f"## {name}（{len(rows)} 位）")
        if not rows:
            lines.append("- 无")
        for row in rows:
            lines.append(f"- **{row['name'] or row['customer_id']}**（{row['stage']}）"
                         f" 风险：{'、'.join(row['risk_tags']) or '无'}")
            for task in row["open_tasks"]:
                lines.append(f"  - 待办：{task}")
            if row["doc_versions"]:
                lines.append(f"  - 文书版本：{len(row['doc_versions'])} 个，可溯源")
        lines.append("")

    total_tasks = sum(len(v) for v in buckets.values())
    return {
        "advisor": advisor,
        "buckets": buckets,
        "total_customers": total_tasks,
        "markdown": "\n".join(lines),
        "note": "交接文档由系统自动生成，AI 生成内容均带版本 ID 与来源索引，可追溯到具体生成轮次。",
    }
