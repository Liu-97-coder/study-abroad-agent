"""网申监控 Agent 的 LangGraph 节点（网申 Agent 步骤 5）。

一次执行完成：表单预校验 → 邮件意图解析 → 截止倒计时分级预警 → 推荐人跟进。
"""
from __future__ import annotations

from ...base.base_agent import BaseAgent
from ...schema.application_schema import ApplicationOutput
from ...schema.state_schema import CustomerState
from ...schema.student_schema import StudentBasicInfo
from .application_form_checker import check_form
from .deadline_watcher import from_school_result
from .email_extract_parser import parse_email
from .referee_reminder import build_reminders, needs_action


class ApplicationAgent(BaseAgent):
    name = "application_agent"

    def _run(self, state: CustomerState) -> CustomerState:
        student = StudentBasicInfo(**{k: v for k, v in state.student_info.items()
                                      if k in StudentBasicInfo.model_fields})
        school_result = (state.agent_outputs.get("school") or {}).get("result") or {}

        # 1) 表单预校验（护照 OCR 做交叉比对）
        passport_entities = self._passport_entities(state)
        form = state.student_info.get("application_form") or {}
        form_errors = check_form(form, student, passport_entities) if form else []
        for error in form_errors:
            if error.level == "低级错误":
                self.tag(state, f"网申低级错误：{error.field_name}", level="高",
                         reason=error.error_msg)

        # 2) 院校邮件意图解析
        mail_infos = []
        for mail in state.student_info.get("emails") or []:
            info = parse_email(mail.get("subject", ""), mail.get("text", ""),
                               self.ctx, state.customer_id)
            mail_infos.append(info)
            if info.mail_intent == "补件通知":
                self.tag(state, "院校要求补件", level="高", reason=f"截止 {info.deadline or '未注明'}")
                self.task(state, f"补交材料：{'、'.join(info.need_supplement) or '见邮件'}",
                          level="紧急", due_date=info.deadline or "", source=self.name)
            elif info.mail_intent == "面试邀请":
                self.task(state, "安排面试辅导与模拟", level="紧急", source=self.name)
            elif info.mail_intent == "押金提醒":
                self.task(state, f"押金缴纳提醒：{info.extra_notice}", level="紧急",
                          due_date=info.deadline or "", source=self.name)

        # 3) 截止倒计时三级预警
        submitted = [p.get("school", "") for p in state.student_info.get("submitted_programs") or []]
        deadline_warnings = from_school_result(school_result, submitted)
        for warn in deadline_warnings:
            level = "紧急" if warn["rank"] >= 2 else "普通"
            self.task(state, f"截止预警（{warn['tier']}）：{warn['school']} {warn['major']} "
                             f"剩 {warn['days_left']} 天", level=level,
                      due_date=warn["deadline"], source=self.name)
            if warn["rank"] == 3:
                self.tag(state, "临近截止未递交", level="高", reason=f"{warn['school']} 剩 {warn['days_left']} 天")

        # 4) 推荐人跟进
        referees = build_reminders(state.student_info.get("referees") or [],
                                   student_name=student.school_name or "the applicant",
                                   school=self._top_school(school_result),
                                   deadline=self._earliest_deadline(school_result))
        for task in needs_action(referees):
            self.task(state, f"跟进推荐人：{task.referee_email} 已等待 {task.days_waiting} 天",
                      level="紧急" if task.days_waiting >= 14 else "普通", source=self.name)
            self.tag(state, "推荐信未提交", level="中", reason=f"{task.referee_email} 超期未交")

        output = ApplicationOutput(form_error_list=form_errors, mail_info_list=mail_infos,
                                   deadline_warn_list=deadline_warnings, referee_todo=referees)
        state.out("application", output.model_dump())
        state.stage = "application"
        return state

    def _passport_entities(self, state: CustomerState) -> dict:
        for item in state.student_info.get("uploaded_files") or []:
            name = item.get("name", "")
            if "护照" in name or "passport" in name.lower():
                doc = self.parse_doc(path=item.get("path"), text=item.get("text"))
                return doc.entities
        return {}

    @staticmethod
    def _top_school(school_result: dict) -> str:
        for key in ("sprint_list", "match_list", "safe_list"):
            items = school_result.get(key) or []
            if items:
                return items[0].get("school_name", "")
        return ""

    @staticmethod
    def _earliest_deadline(school_result: dict) -> str:
        rows = []
        for key in ("sprint_list", "match_list", "safe_list"):
            for item in school_result.get(key) or []:
                if item.get("deadline"):
                    rows.append((item.get("days_left", 999), item["deadline"]))
        return sorted(rows)[0][1] if rows else ""
