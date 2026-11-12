"""缺失材料比对 + 分级待办（材料 Agent 步骤 5）。"""
from __future__ import annotations

from ...schema.material_schema import MaterialItem
from ...utils.date_utils import days_until

URGENT_DAYS = 15


def missing_diff(items: list[MaterialItem], uploaded_names: list[str]) -> list[MaterialItem]:
    uploaded = {name.strip() for name in uploaded_names}
    missing = []
    for item in items:
        # 模糊匹配："成绩单" 能命中 "中英文成绩单"
        hit = any(item.material_name in name or name in item.material_name for name in uploaded)
        if item.is_required and not hit:
            missing.append(item)
    return missing


def build_todo(missing: list[MaterialItem], days_to_deadline: int | None,
               source: str = "material_agent") -> list[dict]:
    tasks = []
    for item in missing:
        item_days = days_until(item.submit_deadline)
        if days_to_deadline is not None and days_to_deadline <= URGENT_DAYS:
            level = "紧急"
        elif item_days is not None and item_days <= URGENT_DAYS:
            level = "紧急"
        elif item_days is not None and item_days < 0:
            level = "延期风险"
        else:
            level = "普通"

        escalate = level == "紧急"
        tasks.append({
            "title": f"催收材料：{item.material_name}",
            "level": level,
            "due_date": item.submit_deadline or "",
            "source": source,
            "escalate": escalate,
            "check_standard": item.check_standard,
        })

    if any(t["level"] == "紧急" for t in tasks):
        tasks.append({
            "title": "紧急缺失材料已同步主管（可能错过本轮递交）",
            "level": "紧急", "due_date": "", "source": source,
            "escalate": True, "check_standard": "",
        })
    return tasks
