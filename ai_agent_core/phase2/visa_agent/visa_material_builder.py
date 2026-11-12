"""签证材料包生成（签证 Agent 步骤 1）。

按国家 + 出资类型分支：
- 资金自存 → 只需存款证明 + 流水
- 父母出资 → 追加出资函 + 亲属关系公证（办理周期最长，必须前置）
英国/澳洲还要肺结核检测；这些细节就是"专业度"的差别。
"""
from __future__ import annotations

from ...schema.student_schema import StudentBasicInfo
from ...schema.visa_schema import VisaMaterialItem

COUNTRY_VISA_MATERIALS: dict[str, list[tuple[str, bool, int, str]]] = {
    "英国": [
        ("CAS 确认函", False, 30, "学校签发，信息与护照一致"),
        ("肺结核检测报告", False, 180, "指定诊所，有效期 6 个月"),
        ("存款证明（28 天存期）", False, 30, "递交前需已存满 28 天"),
        ("ATAS 证明（部分专业）", False, 60, "理工科敏感专业需提前申请"),
    ],
    "澳洲": [
        ("COE 确认函", False, 30, "学校签发"),
        ("OSHC 海外学生保险", False, 365, "覆盖全部学习期"),
        ("资金证明（6 个月流水）", False, 30, "部分情况可简化"),
    ],
    "香港": [("学生签注", False, 30, "学校代办，需 6-8 周"),
             ("存款证明", False, 30, "覆盖首年费用")],
    "加拿大": [("GIC 存款证明", False, 60, "指定银行"),
               ("体检回执", False, 180, "指定医院"),
               ("学习许可申请", False, 30, "SDS 或普通通道")],
    "新加坡": [("IPA 原则批准函", False, 60, "学校申请"),
               ("存款证明", False, 30, "覆盖学费生活费")],
    "美国": [("I-20 表格", False, 30, "学校签发"),
             ("SEVIS I-901 缴费凭证", False, 30, "签证前完成"),
             ("DS-160 确认页", False, 30, "在线填写")],
    "欧洲": [("资金担保证明", True, 30, "部分国家需公证"),
             ("住宿证明", False, 30, "租房合同或宿舍确认")],
}

BASE_VISA = [
    ("护照原件及复印件", False, 180, "有效期覆盖学习期后 6 个月"),
    ("签证申请表", False, 30, "在线填写后打印签字"),
    ("证件照", False, 180, "近 6 个月白底，符合各国规格"),
    ("录取通知书 Offer", False, 365, "无条件 Offer 或 CAS/COE"),
    ("学术材料（成绩单/毕业证）", False, 365, "中英文盖章件"),
    ("语言成绩单", False, 730, "2 年有效期内"),
]

PARENT_FUNDED_VISA = [
    ("父母出资函", False, 60, "中英文，父母签字"),
    ("亲属关系公证", True, 90, "公证办理周期 2-3 周，务必前置"),
    ("父母收入证明", False, 60, "单位盖章 + 近 6 个月工资流水"),
]


def build_visa_materials(student: StudentBasicInfo, country: str | None = None,
                         fund_from_parent: bool = True) -> list[VisaMaterialItem]:
    country = country or (student.target_country or ["英国"])[0]
    rows = list(BASE_VISA) + COUNTRY_VISA_MATERIALS.get(country, COUNTRY_VISA_MATERIALS["英国"])
    if fund_from_parent:
        rows += PARENT_FUNDED_VISA

    seen, items = set(), []
    for idx, (name, notarize, valid_days, remark) in enumerate(rows, 1):
        if name in seen:
            continue
        seen.add(name)
        items.append(VisaMaterialItem(material_name=name, need_notarize=notarize,
                                      valid_days=valid_days, is_required=True,
                                      order=idx, remark=remark))
    # 公证类材料办理周期长，排到最前面
    items.sort(key=lambda x: (not x.need_notarize, x.order))
    return items
