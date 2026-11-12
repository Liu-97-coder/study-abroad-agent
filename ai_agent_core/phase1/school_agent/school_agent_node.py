"""选校 Agent 的 LangGraph 节点封装（选校 Agent 步骤 7）。

把抽取 → 筛选 → 分层 → 报告 → 话术 → 纪要 串成一次完整执行，
结果全部写进 state，供下游文书 Agent 直接复用（不用重复抽取/检索）。
"""
from __future__ import annotations

from ...base.base_agent import BaseAgent
from ...schema.school_schema import SchoolResult
from ...schema.state_schema import CustomerState
from ...schema.student_schema import StudentBasicInfo
from .chat_summary import summarize
from .report_generator import generate_report
from .school_filter import filter_schools
from .school_score import split_into_three
from .student_extract import build_followup, extract_student
from .talk_generator import generate_talk


class SchoolAgent(BaseAgent):
    name = "school_agent"

    def _run(self, state: CustomerState) -> CustomerState:
        chat_text = str(state.student_info.pop("raw_chat", "") or "")
        questions = state.student_info.pop("customer_questions", "") or ""

        # 1) 学生背景抽取（规则 + LLM 双路）
        student = extract_student(chat_text, ctx=self.ctx,
                                  existing=state.student_info,
                                  customer_id=state.customer_id)
        # 合并而不是覆盖：uploaded_files / experiences / emails 等后续 Agent 的输入必须保留
        state.student_info = {**state.student_info, **student.model_dump()}
        for tag in student.risk_tags:
            self.tag(state, tag, level="中", reason="学生背景抽取识别")

        # 2) 知识库筛选 + 3) 三档分层
        filtered = filter_schools(self.rag, student)
        buckets = split_into_three(filtered.candidates, student)
        result = SchoolResult(
            sprint_list=buckets["冲刺"], match_list=buckets["匹配"], safe_list=buckets["保底"],
            filtered_out=filtered.dropped,
            sources=[c["source_id"] for c in filtered.candidates],
        )
        total = len(result.all_items())
        if total == 0:
            self.tag(state, "院校库无匹配", level="高", reason="知识库未命中可用院校")
            self.task(state, "补充院校库数据后重跑选校", level="紧急", source=self.name)

        # 4) 反幻觉校验：每所学校必须带 source_id
        missing_source = self.safety.verify_citations([i.model_dump() for i in result.all_items()])
        if missing_source:
            self.tag(state, "院校数据缺溯源", level="高", reason=f"{len(missing_source)} 条无 source_id")

        # 5) 评估报告 + 6) 合规话术 + 7) 咨询纪要
        report = generate_report(student, result, self.ctx, state.customer_id)
        # 只把"结构性风险"打成标签；"被剔除 N 所"属于信息，不是风险
        for shortage in report["facts"]["shortages"]:
            if not shortage.startswith("保底档"):
                continue
            self.tag(state, shortage, level="中", reason="评估报告识别")

        talk = generate_talk(questions, student, self.ctx, state.customer_id) if questions else None
        summary = summarize(chat_text, student, self.ctx, state.customer_id)
        followup = build_followup(student, self.ctx, state.customer_id)

        result.student_summary = "；".join(
            f"{k}:{v}" for k, v in list(report["facts"]["hardware"].items())[:4])
        result.apply_suggest = "；".join(report["facts"]["suggestions"][:3])
        result.overall_risk = report["facts"]["difficulty"]

        state.out("school", {
            "student": student.model_dump(),
            "result": result.model_dump(),
            "report": report,
            "talk": talk,
            "summary": summary,
            "followup": followup,
            "warnings": filtered.warnings,
        })

        # 8) 待办：顾问必须人工确认方案才能推进（AI 不自主决策）
        level = "紧急" if "时间紧张" in student.risk_tags else "普通"
        self.task(state, "顾问确认三档选校方案并回复客户", level=level, source=self.name)
        if followup:
            self.task(state, "发送信息补充追问话术", level="普通", source=self.name)
        if state.stage in {"clue", "consult"}:
            state.stage = "consult"
        return state


def run_school_agent(state: CustomerState, ctx) -> CustomerState:
    """不做状态机、单独跑一次选校（给 API 直接调用）。"""
    return SchoolAgent(ctx).run(state)
