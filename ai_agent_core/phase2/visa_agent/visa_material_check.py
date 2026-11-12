"""签证材料交叉校验与缺失提醒（签证 Agent 步骤 4）。"""
from __future__ import annotations

from ...schema.visa_schema import VisaMaterialItem

LONG_CYCLE_WORDS = ("公证", "肺结核", "体检", "GIC", "ATAS")


def diff_materials(items: list[VisaMaterialItem], uploaded_names: list[str]) -> list[VisaMaterialItem]:
    uploaded = {n.strip() for n in uploaded_names}
    missing = []
    for item in items:
        hit = any(item.material_name in name or name in item.material_name for name in uploaded)
        if item.is_required and not hit:
            missing.append(item)
    return missing


def build_reminders(missing: list[VisaMaterialItem]) -> list[dict]:
    tasks = []
    for item in missing:
        long_cycle = item.need_notarize or any(w in item.material_name for w in LONG_CYCLE_WORDS)
        tasks.append({
            "title": f"签证材料缺失：{item.material_name}",
            "level": "紧急" if long_cycle else "普通",
            "reason": "办理周期长，需前置" if long_cycle else "常规材料",
            "student_text": f"还需要你提供：{item.material_name}（{item.remark}），"
                            f"这个大概需要 {max(item.valid_days // 30, 1)} 个月内有效的版本，麻烦尽快准备～",
        })
    tasks.sort(key=lambda x: x["level"] != "紧急")
    return tasks
