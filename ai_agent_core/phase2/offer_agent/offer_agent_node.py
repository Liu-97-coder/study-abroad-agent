"""Cond Offer 解析 Agent 的 LangGraph 节点（Offer Agent 步骤 5）。"""
from __future__ import annotations

from ...base.base_agent import BaseAgent
from ...schema.offer_schema import OfferFullOutput
from ...schema.state_schema import CustomerState
from ...schema.student_schema import StudentBasicInfo
from .cas_material_builder import build_plan
from .cond_risk_calculator import assess_all
from .offer_ocr_parser import parse_offer
from .offer_policy_matcher import detect_conflict, match_policy, refund_risk, urgency


class OfferAgent(BaseAgent):
    name = "offer_agent"

    def _run(self, state: CustomerState) -> CustomerState:
        student = StudentBasicInfo(**{k: v for k, v in state.student_info.items()
                                      if k in StudentBasicInfo.model_fields})

        offer_file = state.student_info.get("offer_file") or {}
        doc = self.parse_doc(path=offer_file.get("path"), text=offer_file.get("text"))
        if doc.errors:
            self.tag(state, "Offer 文件解析失败", level="高", reason="；".join(doc.errors))
        if doc.confidence and doc.confidence < 0.5:
            self.tag(state, "Offer 识别不完整", level="中", reason="建议人工复核原文")

        parsed = parse_offer(doc.raw_text or str(offer_file.get("text", "")),
                             self.ctx, state.customer_id)
        info = parsed["info"]
        conditions, overall = assess_all(parsed["conditions"], student)

        school_name = info.get("school_name") or state.student_info.get("target_school", "")
        policy, sources = match_policy(school_name, info.get("major", ""), self.ctx)
        policy.policy_conflict = detect_conflict(str(info.get("deadline", "")), policy)
        if policy.policy_conflict:
            self.tag(state, "Offer 与官网政策冲突", level="高", reason=policy.policy_conflict)

        refund = refund_risk(policy)
        if refund == "高":
            self.tag(state, "押金不退政策", level="高", reason="需提前书面告知客户")
        if urgency(policy):
            self.task(state, urgency(policy), level="紧急", source=self.name)

        plan = build_plan(policy, intake_date=str(info.get("intake", "")))
        if plan["risk"]:
            self.tag(state, "CAS 时间紧张", level="高", reason=plan["risk"])
            self.task(state, plan["risk"], level="紧急", source=self.name)

        for cond in conditions:
            if cond.reach_risk == "高":
                self.tag(state, f"Con 条件无法达标：{cond.cond_type}", level="高",
                         reason=cond.gap or cond.improve_suggest)
                self.task(state, f"{cond.cond_type}达标方案：{cond.improve_suggest}",
                          level="紧急", source=self.name)

        output = OfferFullOutput(
            school_name=school_name, major=str(info.get("major", "")),
            intake=str(info.get("intake", "")),
            is_conditional=bool(info.get("is_conditional", True)),
            cond_list=conditions, policy_info=policy,
            cas_time_timeline=plan["timeline"], overall_risk=overall,
            raw_extract={**info, "payment": parsed["payment"]},
        )
        state.out("offer", {**output.model_dump(), "policy_sources": sources,
                            "cas_materials": plan["materials"], "days_to_uncon": plan["days_to_uncon"]})
        state.stage = "offer"
        return state
