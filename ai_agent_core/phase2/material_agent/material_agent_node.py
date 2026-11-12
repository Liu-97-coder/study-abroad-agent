"""材料 Agent 的 LangGraph 节点（材料 Agent 步骤 6）。

一次执行完成：生成清单 → 校验已上传 → 比对缺失 → 生成分级待办与催收文案。
"""
from __future__ import annotations

from ...base.base_agent import BaseAgent
from ...schema.material_schema import MaterialCheckRisk, MaterialFullOutput
from ...schema.state_schema import CustomerState
from ...schema.student_schema import StudentBasicInfo
from ...utils.date_utils import days_until
from .material_list_builder import build_custom_material_list
from .material_llm_check import cross_check, review_with_llm
from .material_notice_generator import generate_notice
from .material_rule_checker import check_material
from .material_task_generator import build_todo, missing_diff


class MaterialAgent(BaseAgent):
    name = "material_agent"

    def _run(self, state: CustomerState) -> CustomerState:
        student = StudentBasicInfo(**{k: v for k, v in state.student_info.items()
                                      if k in StudentBasicInfo.model_fields})
        deadline = self._earliest_deadline(state)

        items, meta = build_custom_material_list(
            student, self.ctx, submit_deadline=deadline,
            language_course=bool(state.student_info.get("language_course")),
            fund_from_parent=bool(state.student_info.get("fund_from_parent", True)))

        uploaded = state.student_info.get("uploaded_files") or []
        checked = []
        for item in uploaded:
            name = item.get("name") or item.get("material_name") or "未命名材料"
            doc = self.parse_doc(path=item.get("path"), text=item.get("text"))
            result = check_material(name, doc, student, meta["country"])

            llm_risks = review_with_llm(name, doc, meta["context"], self.ctx, state.customer_id)
            for risk in llm_risks or []:
                result.risk_list.append(MaterialCheckRisk(
                    risk_level=str(risk.get("risk_level", "中")),
                    risk_desc=str(risk.get("risk_desc", ""))[:200],
                    fix_suggest=str(risk.get("fix_suggest", ""))[:200],
                    material_name=name))
                if risk.get("risk_level") == "高":
                    result.pass_flag = False
            checked.append(result)

        for problem in cross_check(checked):
            self.tag(state, f"材料交叉核对异常：{problem['issue'][:20]}", level="中",
                     reason=str(problem))

        passed_names = [r.material_name for r in checked if r.pass_flag]
        missing = missing_diff(items, passed_names)
        all_risk = [r for item in checked for r in item.risk_list]
        high_risk = [r for r in all_risk if r.risk_level == "高"]

        for risk in high_risk:
            self.tag(state, f"材料高危：{risk.material_name}", level="高", reason=risk.risk_desc)

        days_left = days_until(deadline) if deadline else None
        overdue = 0
        if days_left is not None and days_left < 0:
            overdue = abs(days_left)

        notice = generate_notice([m.material_name for m in missing], overdue,
                                 meta["country"], self.ctx, state.customer_id)
        todo = build_todo(missing, days_left)
        for task in todo:
            self.task(state, task["title"], level=task["level"],
                      due_date=task["due_date"], source=self.name)
        if any(t["escalate"] for t in todo):
            self.tag(state, "材料缺失高危待办", level="高", reason="递交临近且材料未齐")

        output = MaterialFullOutput(
            material_list=items,
            uploaded_check_results=checked,
            missing_materials=[m.material_name for m in missing],
            all_risk=all_risk,
            todo_task_list=[t["title"] for t in todo],
            notice_text=notice["student_text"],
        )
        state.out("material", {**output.model_dump(),
                               "policy_sources": meta["sources"],
                               "days_left": days_left})
        state.stage = "material" if missing else "document"
        return state

    @staticmethod
    def _earliest_deadline(state: CustomerState) -> str:
        school = (state.agent_outputs.get("school") or {}).get("result") or {}
        deadlines = []
        for key in ("sprint_list", "match_list", "safe_list"):
            for item in school.get(key, []) or []:
                left = item.get("days_left")
                if item.get("deadline") and left is not None:
                    deadlines.append((left, item["deadline"]))
        if deadlines:
            return sorted(deadlines)[0][1]
        return ""
