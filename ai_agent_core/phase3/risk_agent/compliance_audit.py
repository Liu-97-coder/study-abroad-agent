"""合规审计：聊天记录巡检（三期模块 A）。

两段式检测：关键词粗筛（快、召回高）→ 语义复核（准、降误报）。
只在这两个条件同时成立时才生成高危工单：
1. 命中红线词
2. 上下文是"正式承诺"而非"客户询问/顾问否认"
"""
from __future__ import annotations

WORKORDER_TEMPLATE = {
    "type": "合规风险工单",
    "action": "主管介入：要求顾问撤回表述并书面说明，留存记录",
}


def audit_messages(messages: list[dict], safety, customer_id: str = "") -> list[dict]:
    workorders: list[dict] = []
    if not messages:
        return workorders

    for msg in messages:
        text = str(msg.get("text", "") or "")
        role = msg.get("role", "advisor")
        if not text.strip():
            continue
        verdict = safety.check(text, use_llm=True, customer_id=customer_id)
        if verdict.level not in {"high", "medium"}:
            continue
        workorders.append({
            "level": "高" if verdict.level == "high" else "中",
            "role": role,
            "hits": verdict.hits,
            "reason": verdict.reason,
            "excerpt": text[:120],
            "action": WORKORDER_TEMPLATE["action"] if verdict.level == "high" else "提示顾问注意措辞",
        })
    return workorders


def scan_batch(customer_messages: dict[str, list[dict]], safety) -> dict[str, list[dict]]:
    """批量巡检全部客户（低峰时段跑，避免占用高峰算力）。"""
    return {cid: audit_messages(msgs, safety, cid) for cid, msgs in customer_messages.items()
            if audit_messages(msgs, safety, cid)}
