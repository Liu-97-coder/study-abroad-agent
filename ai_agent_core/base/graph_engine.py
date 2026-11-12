"""LangGraph 多 Agent 调度引擎（基座任务 3）。

职责：客户状态机 + 分支路由 + 全局记忆 + 全链路日志。
装有 langgraph 时走真正的 StateGraph；没有则用等价的确定性路由循环，
两条路径调用的都是同一批 Agent 节点函数，行为一致。
"""
from __future__ import annotations

from ..schema.state_schema import CustomerState
from .base_agent import BaseAgent

# 演示/自测模式下，Agent 完成后自动推进到的下一阶段。
# 生产环境必须由顾问在界面上点"确认"，AI 不得自主推进（PRD 第八条）。
PIPELINE = {
    "school_agent": "signed",
    "material_agent": "document",
    "document_agent": "application",
    "application_agent": "offer",
    "offer_agent": "visa",
    "visa_agent": "finished",
}

# 阶段 → 该阶段该跑的 Agent
STAGE_AGENT = {
    "clue": "school_agent",
    "consult": "school_agent",
    "signed": "material_agent",
    "material": "material_agent",
    "document": "document_agent",
    "application": "application_agent",
    "offer": "offer_agent",
    "visa": "visa_agent",
}

try:  # langgraph 是可选依赖
    from langgraph.graph import END, StateGraph  # type: ignore

    _LANGGRAPH_OK = True
except Exception:  # noqa: BLE001
    END = "__end__"  # type: ignore
    StateGraph = None  # type: ignore
    _LANGGRAPH_OK = False


class GraphEngine:
    def __init__(self, ctx, agents: dict[str, BaseAgent]):
        self.ctx = ctx
        self.logger = ctx.logger
        self.agents = agents
        self.risk_agent = agents.get("risk_agent")
        self.app = None
        if ctx.settings.use_langgraph and _LANGGRAPH_OK:
            try:
                self.app = self._build_langgraph()
            except Exception as exc:  # noqa: BLE001 - 构建失败就用确定性循环
                self.logger.event("graph", "langgraph_build_failed", level="WARN", error=str(exc))
                self.app = None

    # ---------------- 路由决策 ----------------
    def next_agent(self, state: CustomerState) -> str | None:
        # 插件式扩展：被显式请求时，在 application/offer 阶段插入面试 Agent，
        # 主流程的阶段映射完全不用改。
        if (state.student_info.get("interview_requested")
                and state.stage in {"application", "offer"}
                and "interview" not in state.agent_outputs):
            return "interview_agent"

        stage = state.stage if state.stage in STAGE_AGENT else "clue"
        candidate = STAGE_AGENT[stage]

        if candidate == "school_agent":
            return None if "school" in state.agent_outputs else "school_agent"

        if candidate == "material_agent":
            material = state.agent_outputs.get("material")
            if material is None:
                return "material_agent"
            if material.get("missing_materials"):
                return None  # 等学生上传，材料 Agent 不在原地打转
            return "document_agent" if "document" not in state.agent_outputs else None

        if candidate == "document_agent":
            return None if "document" in state.agent_outputs else "document_agent"

        if candidate == "application_agent":
            return None if "application" in state.agent_outputs else "application_agent"

        if candidate == "offer_agent":
            return None if "offer" in state.agent_outputs else "offer_agent"

        if candidate == "visa_agent":
            return None if "visa" in state.agent_outputs else "visa_agent"

        return None

    # ---------------- 执行 ----------------
    def run(self, state: CustomerState, max_steps: int | None = None,
            auto_advance: bool = False) -> CustomerState:
        max_steps = max_steps or self.ctx.settings.graph_max_steps
        if self.app is not None:
            try:
                result = self.app.invoke({"state": state, "auto_advance": auto_advance},
                                         {"recursion_limit": max_steps * 3})
                return CustomerState(**result["state"])
            except Exception as exc:  # noqa: BLE001
                self.logger.event("graph", "langgraph_invoke_failed", level="WARN", error=str(exc))

        # 兜底：确定性循环（逻辑与 langgraph 版本完全一致）
        steps = 0
        while steps < max_steps:
            nxt = self.next_agent(state)
            if not nxt:
                break
            state = self.agents[nxt].run(state)
            self._after_agent(state, nxt, auto_advance)
            if self.risk_agent:
                try:
                    state = self.risk_agent.run(state)
                except Exception:  # noqa: BLE001 - 风控并行失败不阻塞主流程
                    pass
            steps += 1
        self.logger.event("graph", "finished", trace_id=state.trace_id,
                          customer_id=state.customer_id, stage=state.stage, steps=steps)
        return state

    def _after_agent(self, state: CustomerState, name: str, auto_advance: bool) -> None:
        if auto_advance and name in PIPELINE:
            state.stage = PIPELINE[name]
            self.logger.event("graph", "stage_advance", trace_id=state.trace_id,
                              customer_id=state.customer_id, stage=state.stage)

    # ---------------- LangGraph 版 ----------------
    def _build_langgraph(self):
        if StateGraph is None:
            raise RuntimeError("langgraph 不可用")

        builder = StateGraph(dict)

        def dispatch(_: dict) -> dict:
            return {}

        builder.add_node("dispatch", dispatch)

        for name in self.agents:
            builder.add_node(name, self._make_node(name))

        builder.set_entry_point("dispatch")
        mapping = {name: name for name in self.agents}
        mapping[END] = END
        builder.add_conditional_edges(
            "dispatch",
            lambda payload: self.next_agent(CustomerState(**payload["state"])) or END,
            mapping,
        )
        for name in self.agents:
            builder.add_edge(name, "dispatch")
        return builder.compile()

    def _make_node(self, name: str):
        def node(payload: dict) -> dict:
            state = CustomerState(**payload["state"])
            state = self.agents[name].run(state)
            self._after_agent(state, name, bool(payload.get("auto_advance")))
            if name != "risk_agent" and self.risk_agent:
                try:
                    state = self.risk_agent.run(state)
                except Exception:  # noqa: BLE001
                    pass
            return {"state": state.model_dump()}

        return node


def build_agents(ctx) -> dict[str, BaseAgent]:
    """注册表：新增 Agent 只需在这里加一行，调度层不用改（插件式扩展）。"""
    from ..phase1.doc_agent.doc_agent_node import DocumentAgent
    from ..phase1.school_agent.school_agent_node import SchoolAgent
    from ..phase2.app_agent.app_agent_node import ApplicationAgent
    from ..phase2.interview_agent.interview_agent_node import InterviewAgent
    from ..phase2.material_agent.material_agent_node import MaterialAgent
    from ..phase2.offer_agent.offer_agent_node import OfferAgent
    from ..phase2.visa_agent.visa_agent_node import VisaAgent
    from ..phase3.risk_agent.risk_agent_node import RiskAgent

    instances = [SchoolAgent(ctx), MaterialAgent(ctx), DocumentAgent(ctx),
                 ApplicationAgent(ctx), InterviewAgent(ctx), OfferAgent(ctx),
                 VisaAgent(ctx), RiskAgent(ctx)]
    return {agent.name: agent for agent in instances}
