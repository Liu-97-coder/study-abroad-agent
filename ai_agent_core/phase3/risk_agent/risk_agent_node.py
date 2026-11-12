"""风控 Agent 的 LangGraph 节点（三期核心）。

定位：**常驻并行**。调度器每跑完一个业务 Agent 就调它一次，它只读不写业务状态，
不阻塞主流程；发现问题就产风险标签 + 工单。
幂等：同一份数据重复调用不会重复建单（按标题去重）。
"""
from __future__ import annotations

from ...base.base_agent import BaseAgent
from ...schema.state_schema import CustomerState
from .compliance_audit import audit_messages
from .handover import build_handover
from .high_risk_predict import predict

LEVEL_RANK = {"低": 0, "中": 1, "高": 2}


class RiskAgent(BaseAgent):
    name = "risk_agent"

    def _run(self, state: CustomerState) -> CustomerState:
        # 1) 聊天记录合规巡检
        messages = state.student_info.get("chat_messages") or []
        workorders = audit_messages(messages, self.safety, state.customer_id)
        for order in workorders:
            if order["level"] == "高":
                self.tag(state, "违规话术工单", level="高", reason=order["reason"])
                self._task_once(state, f"合规工单复核：{order['excerpt'][:20]}", "紧急")

        # 2) 高危客户预判
        prediction = predict(state)
        if prediction["level"] != "低":
            for tag in prediction["tags"]:
                self.tag(state, tag, level=prediction["level"], reason="多维风险打分")
            if prediction["level"] == "高":
                self._task_once(state, f"高危客户介入（风险分 {prediction['score']}）", "紧急")

        # 3) 交接清单快照（顾问离职时可直接导出）
        handover = build_handover("当前顾问", [state], self.storage)

        state.out("risk", {
            "workorders": workorders,
            "prediction": prediction,
            "handover_preview": handover["markdown"][:800],
            "overall_level": max(prediction["level"], "高" if workorders else "低",
                                 key=lambda x: LEVEL_RANK[x]),
        })
        return state

    def _task_once(self, state: CustomerState, title: str, level: str) -> None:
        if any(t.get("title") == title for t in state.task_list):
            return
        self.task(state, title, level=level, source=self.name)
