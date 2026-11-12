"""面试模拟 Agent（第八个 Agent，验证插件式扩展）。

它做三件事：
1. 按目标专业/国家生成一份"模拟面试卷"（6 题，带考察点与参考要点）
2. 学生逐题作答，五维打分 + 一句最关键的改进建议
3. 汇总成复盘报告（最弱三题 + 五维平均 + 下一步动作）

注意：它**不**进入主流程的必经路径 —— 只有 `student_info.interview_requested=True`
且阶段到了 application/offer 才会被路由唤醒。加一个 Agent 不用改主流程。
"""
from __future__ import annotations

import uuid
from datetime import datetime

from ...base.base_agent import BaseAgent
from ...schema.interview_schema import InterviewSession
from ...schema.state_schema import CustomerState
from ...schema.student_schema import StudentBasicInfo
from .answer_scorer import build_report, score_answer
from .question_bank import pick_with_rag


def _target_text(student: StudentBasicInfo) -> str:
    country = "/".join(student.target_country) or "未定"
    return f"{country}·{student.target_degree or '硕士'}·{student.target_major or '未定'}"


def start_session(customer_id: str, student: StudentBasicInfo, ctx,
                  count: int = 6) -> InterviewSession:
    questions = pick_with_rag(ctx, student, count=count)
    session = InterviewSession(
        session_id="iv-" + uuid.uuid4().hex[:8],
        customer_id=customer_id,
        target=_target_text(student),
        questions=questions,
        created_at=datetime.now().isoformat(timespec="seconds"),
    )
    return session


def answer_question(session: InterviewSession, qid: str, answer: str, ctx,
                    customer_id: str = "") -> InterviewSession:
    question = next((q for q in session.questions if q.qid == qid), None)
    if question is None:
        raise ValueError(f"题目不存在：{qid}")
    score = score_answer(question, answer, ctx, customer_id)
    session.answers = [a for a in session.answers if a.qid != qid] + [score]
    session.avg_score = round(sum(a.total for a in session.answers) / len(session.answers), 1)
    session.report = build_report(session)
    return session


class InterviewAgent(BaseAgent):
    name = "interview_agent"

    def _run(self, state: CustomerState) -> CustomerState:
        student = StudentBasicInfo(**{k: v for k, v in state.student_info.items()
                                      if k in StudentBasicInfo.model_fields})
        count = int(state.student_info.get("interview_question_count") or 6)
        session = start_session(state.customer_id, student, self.ctx, count=count)

        self.storage.save_interview(session)
        state.out("interview", session.model_dump())
        self.task(state, f"安排模拟面试（{len(session.questions)} 题已生成，链接见面试 Tab）",
                  level="普通", source=self.name)
        for q in session.questions[:2]:
            self.logger.event(self.name, "question", customer_id=state.customer_id,
                              qid=q.qid, category=q.category)
        return state
