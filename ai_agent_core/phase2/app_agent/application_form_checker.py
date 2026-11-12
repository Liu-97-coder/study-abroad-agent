"""网申表单预校验（网申 Agent 步骤 1）。

最容易出低级错误的地方：姓名拼音、护照号、GPA、专业代码。
校验思路：把网申表单和 OCR 出来的护照/成绩单做交叉比对，不一致就拦下来。
"""
from __future__ import annotations

import re

from ...schema.application_schema import FormCheckError
from ...schema.student_schema import StudentBasicInfo


def _pinyin(text: str) -> str:
    return re.sub(r"[^A-Za-z\s]", "", text or "").upper().strip()


def check_form(form: dict, student: StudentBasicInfo,
               passport_entities: dict | None = None) -> list[FormCheckError]:
    errors: list[FormCheckError] = []
    passport_entities = passport_entities or {}

    # 身份类：与护照 OCR 交叉比对
    form_name = _pinyin(str(form.get("name_pinyin", "")))
    passport_name = _pinyin(str(passport_entities.get("name", "")))
    if form_name and passport_name and form_name.replace(" ", "") != passport_name.replace(" ", ""):
        errors.append(FormCheckError(field_name="姓名拼音", level="低级错误",
                                     error_msg=f"表单填写 {form_name} 与护照 {passport_name} 不一致",
                                     suggest_value=passport_name))

    form_passport = str(form.get("passport_no", "")).strip().upper()
    real_passport = str(passport_entities.get("passport_no", "")).strip().upper()
    if form_passport and real_passport and form_passport != real_passport:
        errors.append(FormCheckError(field_name="护照号", level="低级错误",
                                     error_msg="护照号与证件不一致（差 1 位就会被拒）",
                                     suggest_value=real_passport))
    if form_passport and not re.fullmatch(r"[EGD]\d{8}", form_passport):
        errors.append(FormCheckError(field_name="护照号", level="低级错误",
                                     error_msg="护照号格式异常，应为 1 位字母 + 8 位数字"))

    # 学术类：GPA 与申报值比对
    form_gpa = form.get("gpa")
    try:
        form_gpa_f = float(form_gpa) if form_gpa not in (None, "") else None
    except (TypeError, ValueError):
        form_gpa_f = None
        errors.append(FormCheckError(field_name="GPA", level="低级错误",
                                     error_msg="GPA 不是有效数字"))
    if form_gpa_f is not None and student.gpa is not None and abs(form_gpa_f - student.gpa) > 0.05:
        errors.append(FormCheckError(field_name="GPA", level="低级错误",
                                     error_msg=f"表单 {form_gpa_f} 与档案 {student.gpa} 不一致",
                                     suggest_value=str(student.gpa)))

    # 申请信息：专业代码 / 申请费 / 轮次
    code = str(form.get("program_code", "")).strip()
    if code and not re.fullmatch(r"[A-Z0-9\-]{4,12}", code):
        errors.append(FormCheckError(field_name="专业代码", level="风险提示",
                                     error_msg="专业代码格式可疑，请对照官网核对"))
    if form.get("application_fee_paid") is False:
        errors.append(FormCheckError(field_name="申请费", level="低级错误",
                                     error_msg="申请费未缴纳，递交不会被受理"))
    if not form.get("round"):
        errors.append(FormCheckError(field_name="申请轮次", level="风险提示",
                                     error_msg="未填写申请轮次，可能影响审核批次"))
    return errors
