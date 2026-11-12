"""推荐人跟进（网申 Agent 步骤 4）。

网申里最容易翻车的一环：推荐信链接发出去，导师 7 天没点。
规则：发送 > 7 天未提交 → 生成英文「温和/加急」两版跟进话术 + 顾问待办。
"""
from __future__ import annotations

from datetime import date

from ...schema.application_schema import RefereeRemindTask
from ...utils.date_utils import days_until, parse_date

REMIND_AFTER_DAYS = 7

SOFT_TEMPLATE = (
    "Subject: Gentle reminder — recommendation letter for {student}\n\n"
    "Dear {referee},\n\nI hope this message finds you well. I am writing to kindly follow up on the "
    "recommendation letter request for {student}'s application to {school}. The submission link was "
    "sent on {sent_date}. If you have any difficulty accessing the portal, please let me know and I "
    "will resend it immediately.\n\nThank you very much for your time and support.\n\nBest regards"
)

URGENT_TEMPLATE = (
    "Subject: Urgent — recommendation letter deadline approaching for {student}\n\n"
    "Dear {referee},\n\nI am writing with regard to the recommendation letter for {student}, whose "
    "application deadline is {deadline}. As the letter has not yet been received, I wanted to check "
    "whether anything is blocking the submission. I am happy to provide a summary of {student}'s "
    "achievements to assist you.\n\nThank you for your continued support.\n\nBest regards"
)


def build_reminders(referees: list[dict], student_name: str = "the applicant",
                    school: str = "", deadline: str = "") -> list[RefereeRemindTask]:
    tasks = []
    today = date.today()
    for referee in referees:
        email = referee.get("email", "")
        sent = referee.get("send_link_date") or referee.get("sent_date", "")
        submitted = bool(referee.get("submitted", False))
        sent_date = parse_date(sent)
        waiting = (today - sent_date).days if sent_date else 0

        content = ""
        if not submitted and waiting >= REMIND_AFTER_DAYS:
            urgent = waiting >= REMIND_AFTER_DAYS * 2
            template = URGENT_TEMPLATE if urgent else SOFT_TEMPLATE
            content = template.format(student=student_name, referee=referee.get("name", "Professor"),
                                     school=school or "the programme",
                                     sent_date=sent or "recently", deadline=deadline or "approaching")

        tasks.append(RefereeRemindTask(
            referee_email=email, send_link_date=sent, days_waiting=waiting,
            remind_content=content, is_submitted=submitted))
    return tasks


def needs_action(tasks: list[RefereeRemindTask]) -> list[RefereeRemindTask]:
    return [t for t in tasks if t.remind_content]
