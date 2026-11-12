"""材料清单匹配引擎（材料 Agent 步骤 1）。

输入：目标国家、学位、在读/毕业、是否语言班
输出：因人而异的材料清单（不是一张通用清单）

设计要点：清单项带 submit_deadline 偏移量（相对递交截止倒推），
这样"催收"才有明确的时间锚点，而不是一句"尽快"。
"""
from __future__ import annotations

from ...schema.material_schema import MaterialItem
from ...schema.student_schema import StudentBasicInfo
from ...utils.date_utils import add_days, parse_date

# (名称, 分类, 是否必交, 校验标准, 相对递交截止提前天数)
BASE_MATERIALS = [
    ("护照首页扫描件", "签证材料", True, "有效期需覆盖入学后 6 个月，姓名拼音与网申一致", 60),
    ("中英文成绩单", "学术材料", True, "学校教务盖章、中英文对照、无涂改", 30),
    ("语言成绩单", "学术材料", True, "雅思/托福官方成绩单，需在 2 年有效期内", 45),
    ("个人简历 CV", "基础材料", True, "一页，量化成果", 20),
    ("个人陈述 PS", "基础材料", True, "绑定真实经历，非模板", 20),
    ("推荐信", "基础材料", True, "2 封（学术+企业优先），需推荐人邮箱网推", 25),
    ("存款证明", "资金材料", True, "余额覆盖首年学费+生活费，存期满足签证国要求", 40),
    ("银行流水", "资金材料", True, "近 6 个月连续流水，无异常大额临存", 40),
]

COUNTRY_MATERIALS = {
    "英国": [("肺结核检测报告", "签证材料", True, "指定诊所出具，有效期 6 个月", 35),
             ("CAS 确认函", "签证材料", True, "信息需与护照完全一致", 30)],
    "澳洲": [("COE 确认函", "签证材料", True, "学校签发", 30),
             ("海外学生保险 OSHC", "签证材料", True, "覆盖全部学习周期", 30)],
    "香港": [("港澳通行证/签注", "签证材料", True, "有效期覆盖学习期", 30)],
    "加拿大": [("GIC 资金证明", "资金材料", True, "指定银行开户", 45),
               ("体检回执", "签证材料", True, "指定医院", 35)],
    "新加坡": [("学生签证 IPA", "签证材料", True, "学校代办", 30)],
    "美国": [("I-20 表格", "签证材料", True, "学校签发", 45),
             ("SEVIS 缴费凭证", "签证材料", True, "SEVIS I-901", 40)],
    "欧洲": [("资金担保证明", "资金材料", True, "按各国要求", 40)],
}

PARENT_FUNDED = [("父母出资函", "资金材料", True, "中英文，父母签字", 35),
                 ("亲属关系公证", "签证材料", True, "户口本/出生证明公证，办理周期 2-3 周", 50)]


def is_in_school(student: StudentBasicInfo) -> bool:
    return (student.grade or "") in {"大一", "大二", "大三", "大四", "研一", "研二", "研三", "应届"}


def build_custom_material_list(student: StudentBasicInfo, ctx=None,
                               submit_deadline: str = "",
                               language_course: bool = False,
                               fund_from_parent: bool = True) -> tuple[list[MaterialItem], dict]:
    rows: list[tuple] = list(BASE_MATERIALS)
    country = (student.target_country or ["英国"])[0]

    if is_in_school(student):
        rows.append(("在读证明", "学术材料", True, "学校盖章，注明预计毕业时间", 30))
    else:
        rows.append(("毕业证 + 学位证", "学术材料", True, "中英文盖章件，或公证件", 30))

    rows += COUNTRY_MATERIALS.get(country, [])
    if language_course:
        rows.append(("语言班录取确认", "签证材料", True, "语言班 CAS/Offer，注意最短课程时长要求", 30))
    if fund_from_parent:
        rows += PARENT_FUNDED

    # 去重（同名保留第一条）
    seen, unique = set(), []
    for row in rows:
        if row[0] in seen:
            continue
        seen.add(row[0])
        unique.append(row)

    deadline = parse_date(submit_deadline)
    items = []
    for name, category, required, standard, offset in unique:
        due = add_days(submit_deadline, -offset) if deadline else ""
        items.append(MaterialItem(material_name=name, is_required=required,
                                  submit_deadline=due, check_standard=standard,
                                  category=category, remark=f"建议在递交前 {offset} 天完成"))

    meta = {"country": country, "sources": [], "context": ""}
    if ctx is not None:
        chunks = ctx.rag.search("visa", f"{country} 签证 材料清单 资金 存期",
                                top_k=6, rerank_top=3)
        if chunks:
            meta["sources"] = [c.source_info.get("source_id", "") for c in chunks]
            meta["context"] = ctx.rag.format_context(chunks, max_chars=1500)
            for item in items:
                if item.category == "资金材料":
                    item.remark += f"；政策依据：{chunks[0].source_info.get('source_id', '')}"
    return items, meta
