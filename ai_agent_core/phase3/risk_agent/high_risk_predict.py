"""高危客户预判（三期模块 B）。

多维度打分 → 三个标签：逾期风险 / 签证风险 / 退费客诉风险。
分数不是玄学，每一项都对应一个可核对的事实（缺几份材料、改了几版文书、差几分）。
"""
from __future__ import annotations

DIMENSIONS = {
    "逾期节点": 25,
    "材料缺失": 20,
    "文书返工": 15,
    "Con条件缺口": 25,
    "负面沟通": 10,
    "时间紧迫": 20,
}


def predict(state) -> dict:
    outputs = state.agent_outputs or {}
    material = outputs.get("material") or {}
    offer = outputs.get("offer") or {}
    document = outputs.get("document") or {}

    urgent_tasks = [t for t in state.task_list if t.get("level") == "紧急"]
    missing = len(material.get("missing_materials") or [])
    rewrites = len((document.get("versions") or {}))
    quality = (document.get("quality") or {}).get("total")
    cond_high = len([c for c in (offer.get("cond_list") or []) if c.get("reach_risk") == "高"])
    negative = 0
    for msg in state.student_info.get("chat_messages") or []:
        text = str(msg.get("text", ""))
        if any(w in text for w in ("退费", "退款", "投诉", "不满意", "差评", "起诉")):
            negative += 1

    facts = {
        "逾期节点": len(urgent_tasks),
        "材料缺失": missing,
        "文书返工": max(0, rewrites - 4),
        "Con条件缺口": cond_high,
        "负面沟通": negative,
        "时间紧迫": 1 if "时间紧张" in state.risk_tags else 0,
    }

    score = 0.0
    reasons = []
    for dim, weight in DIMENSIONS.items():
        value = facts[dim]
        if value <= 0:
            continue
        ratio = min(1.0, value / (3 if dim in {"逾期节点", "材料缺失", "Con条件缺口"} else 2))
        score += weight * ratio
        reasons.append(f"{dim}={value}")
    score = round(min(100.0, score), 1)

    tags = []
    if facts["逾期节点"] >= 1 or facts["时间紧迫"]:
        tags.append("逾期风险")
    if facts["Con条件缺口"] >= 1 or "签证时间不足 45 天" in state.risk_tags:
        tags.append("签证风险")
    if facts["负面沟通"] >= 1 or (quality is not None and quality < 60) or facts["文书返工"] >= 2:
        tags.append("退费客诉风险")

    level = "高" if score >= 60 else ("中" if score >= 30 else "低")
    return {"score": score, "level": level, "tags": tags, "facts": facts,
            "reasons": reasons or ["暂未发现明显风险信号"]}


def batch_predict(states: list) -> list[dict]:
    rows = []
    for state in states:
        result = predict(state)
        if result["level"] != "低":
            rows.append({"customer_id": state.customer_id, **result})
    return sorted(rows, key=lambda x: x["score"], reverse=True)
