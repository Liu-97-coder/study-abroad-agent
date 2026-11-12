"""材料合规硬规则校验（材料 Agent 步骤 3）。

规则层负责"确定性错误"：存期不够、没过盖章、金额不足、证件过期 —— 这些不需要
大模型判断，写死规则反而更准、更便宜、可解释。LLM 只在规则识别不到时兜底。
"""
from __future__ import annotations

from ...schema.material_schema import MaterialCheckRisk, MaterialCheckResult
from ...schema.student_schema import StudentBasicInfo

# 各国签证资金最低要求（人民币口径，仅作规则演示，实际以当年移民局公告为准）
FUND_REQUIREMENT = {"英国": 350000, "澳洲": 300000, "香港": 200000, "加拿大": 250000,
                    "新加坡": 250000, "美国": 400000, "欧洲": 200000}
# 法定最低存期（天）
DEPOSIT_DAYS_REQUIREMENT = {"英国": 28, "澳洲": 180, "加拿大": 120, "香港": 0,
                            "新加坡": 0, "美国": 0, "欧洲": 0}


def _risk(level: str, desc: str, fix: str, material: str) -> MaterialCheckRisk:
    return MaterialCheckRisk(risk_level=level, risk_desc=desc, fix_suggest=fix,
                             material_name=material)


def check_material(material_name: str, doc, student: StudentBasicInfo,
                   country: str) -> MaterialCheckResult:
    name = material_name or ""
    entities = getattr(doc, "entities", {}) or {}
    raw = (getattr(doc, "raw_text", "") or "")
    risks: list[MaterialCheckRisk] = []

    if "成绩单" in name:
        if not any(k in raw for k in ("英文", "English", "TRANSCRIPT", "Transcript")):
            risks.append(_risk("高", "未见英文版本", "回学校教务处开具中英文对照成绩单并盖章", name))
        if not any(k in raw for k in ("盖章", "公章", "教务", "Seal", "SEAL")):
            risks.append(_risk("中", "未识别到盖章信息", "确认是否有教务章，扫描件需清晰可见", name))
        gpa = entities.get("gpa") or entities.get("average_score")
        if gpa and student.gpa:
            base = gpa if gpa <= 5 else gpa / 25
            if abs(base - student.gpa) > 0.3:
                risks.append(_risk("高", f"成绩单 GPA {gpa} 与申报 {student.gpa} 不一致",
                                   "核对申报值，网申填错会被判材料造假", name))
        if "涂改" in raw:
            risks.append(_risk("高", "疑似涂改痕迹", "重新开具原件，涂改件一律不可用", name))

    elif "存款证明" in name:
        need = FUND_REQUIREMENT.get(country, 300000)
        amount = entities.get("fund_amount")
        if amount is None:
            risks.append(_risk("中", "未识别到存款金额", "上传清晰完整页，需显示户名、金额、存入日", name))
        elif amount < need:
            risks.append(_risk("高", f"存款 {amount:,.0f} 元低于 {country} 建议 {need:,.0f} 元",
                               "补充存款或增加父母资金证明，覆盖首年学费+生活费", name))
        days_need = DEPOSIT_DAYS_REQUIREMENT.get(country, 0)
        if days_need:
            have = entities.get("deposit_days")
            if have is None:
                risks.append(_risk("中", f"未识别到存期，{country} 要求至少 {days_need} 天",
                                   "开具带存入日期的存款证明，按 28 天规则倒排", name))
            elif have < days_need:
                risks.append(_risk("高", f"存期 {have} 天不足 {days_need} 天",
                                   f"延长存款时间至满 {days_need} 天后再递签", name))

    elif "流水" in name:
        if not raw.strip():
            risks.append(_risk("中", "流水内容为空", "补传近 6 个月银行流水", name))
        if entities.get("fund_amount") and entities["fund_amount"] > 200000:
            risks.append(_risk("中", "存在单笔较大金额", "准备资金来源说明（工资/理财赎回/卖房）",
                               name))

    elif "护照" in name:
        if not entities.get("passport_no"):
            risks.append(_risk("高", "未识别到护照号", "上传资料页，确保 MRZ 区清晰", name))
        if "有效期" not in raw and "Expiry" not in raw:
            risks.append(_risk("中", "未见有效期信息", "确认有效期覆盖入学后 6 个月", name))

    elif "在读证明" in name:
        if not any(k in raw for k in ("在读", "预计毕业", "学籍")):
            risks.append(_risk("中", "未见在读/预计毕业信息", "开具标准在读证明并盖章", name))

    elif "毕业证" in name:
        grad_year = entities.get("graduation_year")
        if grad_year and student.intake_year and grad_year > student.intake_year:
            risks.append(_risk("高", "毕业时间晚于入学时间", "核对学制，可能需要延期入学", name))

    elif "语言" in name:
        if not (entities.get("ielts") or entities.get("toefl")):
            risks.append(_risk("中", "未识别到语言分数", "上传官方成绩单（非截图）", name))

    elif "肺结核" in name:
        if "阴性" not in raw and "negative" not in raw.lower():
            risks.append(_risk("中", "未见检测结论", "上传完整报告，含结论页", name))

    else:
        if not raw.strip():
            risks.append(_risk("中", "文件内容为空或无法识别", "重新上传清晰版本", name))

    for warning in getattr(doc, "warnings", []) or []:
        risks.append(_risk("低", warning, "人工复核", name))

    passed = not any(r.risk_level == "高" for r in risks)
    return MaterialCheckResult(material_name=name, pass_flag=passed, risk_list=risks,
                               extracted=entities,
                               upload_file_id=getattr(doc, "file_type", None))
