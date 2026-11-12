"""签证智能审核 Agent 的 LangGraph 节点（签证 Agent 步骤 5）。"""
from __future__ import annotations

from ...base.base_agent import BaseAgent
from ...schema.state_schema import CustomerState
from ...schema.student_schema import StudentBasicInfo
from ...schema.visa_schema import VisaFullOutput
from .fund_risk_analyzer import analyze_fund
from .visa_material_builder import build_visa_materials
from .visa_material_check import build_reminders, diff_materials
from .visa_timeline_planner import plan_timeline


class VisaAgent(BaseAgent):
    name = "visa_agent"

    def _run(self, state: CustomerState) -> CustomerState:
        student = StudentBasicInfo(**{k: v for k, v in state.student_info.items()
                                      if k in StudentBasicInfo.model_fields})
        country = (student.target_country or ["英国"])[0]
        fund_from_parent = bool(state.student_info.get("fund_from_parent", True))

        # 1) 材料包
        items = build_visa_materials(student, country, fund_from_parent)

        # 2) 资金风险推理
        fund_data = dict(state.student_info.get("fund_data") or {})
        if not fund_data:
            for uploaded in state.student_info.get("uploaded_files") or []:
                if "存款" in uploaded.get("name", ""):
                    doc = self.parse_doc(path=uploaded.get("path"), text=uploaded.get("text"))
                    fund_data = {"amount": doc.entities.get("fund_amount"),
                                 "deposit_days": doc.entities.get("deposit_days"),
                                 "deposit_date": doc.entities.get("deposit_date")}
                    break
        fund_risks, amount, fund_level = analyze_fund(fund_data, country, self.ctx,
                                                     state.customer_id)
        for risk in fund_risks:
            if risk.risk_level == "高":
                self.tag(state, f"签证资金风险：{risk.risk_tag}", level="高", reason=risk.reason)

        # 3) 时间线
        arrival = str(state.student_info.get("arrival_date") or "")
        cas_date = str(state.student_info.get("cas_date") or "")
        timeline = plan_timeline(arrival, cas_date, country)
        if timeline["risk"] == "高":
            self.tag(state, "签证时间不足 45 天", level="高", reason=timeline["warn"])
            self.task(state, timeline["warn"], level="紧急", source=self.name)
        for todo in timeline["todo"]:
            self.task(state, todo, level="普通", source=self.name)

        # 4) 缺失材料比对
        uploaded_names = [u.get("name", "") for u in state.student_info.get("uploaded_files") or []]
        missing = diff_materials(items, uploaded_names)
        for reminder in build_reminders(missing):
            self.task(state, reminder["title"], level=reminder["level"], source=self.name)
        if any(r["level"] == "紧急" for r in build_reminders(missing)):
            self.tag(state, "签证长周期材料缺失", level="高", reason="公证/体检类材料未启动")

        output = VisaFullOutput(
            target_country=country, fund_total=amount,
            fund_risk_list=fund_risks, visa_material_list=items,
            time_timeline=timeline["nodes"],
            missing_materials=[m.material_name for m in missing],
            todo_task_list=timeline["todo"],
            overall_risk="高" if fund_level == "高" or timeline["risk"] == "高" else (
                "中" if fund_level == "中" or timeline["risk"] == "中" else "低"),
        )
        state.out("visa", output.model_dump())
        state.stage = "visa"
        return state
