"""学生背景结构化抽取（选校 Agent 步骤 1）。

双路设计：
- 规则路：正则抽出 GPA / 雅思 / 国家 / 预算 / 实习段数，永远可跑，可解释
- LLM 路：把整段聊天丢给模型做"补漏"，失败就退回规则结果

为什么要双路？留学场景里 GPA、语言分数一旦抽错，整个选校方案全废。
规则路保证"有据可查"，LLM 路负责"读懂口语表达"，两者交叉才敢往下走。
"""
from __future__ import annotations

import re

from ...prompt.extract_prompt import EXTRACT_STUDENT_PROMPT, EXTRACT_STUDENT_SYSTEM, FOLLOWUP_PROMPT
from ...schema.student_schema import StudentBasicInfo
from ...utils.score_utils import gpa_to_4, percent_to_gpa4

COUNTRY_ALIASES = {
    "英国": ["英国", "英硕", "uk", "united kingdom", "英格兰", "苏格兰"],
    "香港": ["香港", "港校", "hk", "hong kong"],
    "澳洲": ["澳洲", "澳大利亚", "australia", "澳硕"],
    "新加坡": ["新加坡", "singapore", "nus", "ntu"],
    "加拿大": ["加拿大", "canada"],
    "美国": ["美国", "usa", "美硕", "america"],
    "欧洲": ["欧洲", "荷兰", "德国", "法国", "爱尔兰", "意大利", "北欧", "europe"],
}

DEGREE_ALIASES = {
    "硕士": ["硕士", "研究生", "master", "msc", "ma ", "meng", "授课型"],
    "本科": ["本科", "学士", "bachelor", "undergraduate"],
    "博士": ["博士", "phd", "doctor"],
}

MAJOR_ALIASES = {
    "计算机": ["计算机", "软件工程", "cs", "computer science", "人工智能", "ai", "数据科学", "data science"],
    "金融": ["金融", "finance", "会计", "accounting", "商科", "business"],
    "传媒": ["传媒", "媒体", "communication", "media", "新闻", "journalism"],
    "教育": ["教育", "education", "tesol", "teaching"],
    "电子工程": ["电子", "电气", "ee", "electronic", "通信", "telecommunication"],
    "机械工程": ["机械", "mechanical", "mechatronics"],
}

SCHOOL_985 = ["清华大学", "北京大学", "复旦大学", "上海交通大学", "浙江大学", "南京大学",
              "中国科学技术大学", "哈尔滨工业大学", "西安交通大学", "武汉大学", "华中科技大学",
              "中山大学", "四川大学", "同济大学", "东南大学", "北京航空航天大学", "天津大学",
              "南开大学", "厦门大学", "山东大学", "吉林大学", "湖南大学", "中南大学", "重庆大学",
              "大连理工大学", "北京理工大学", "华南理工大学", "电子科技大学", "西北工业大学",
              "东北大学", "兰州大学", "中国农业大学", "华东师范大学", "南京理工大学"]

_CN_NUM = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8}
_REQUIRED = ["gpa/average_score", "语言成绩", "target_country", "target_major", "intake_year", "target_degree"]


def _int(value: str) -> int:
    value = value.strip()
    return int(value) if value.isdigit() else _CN_NUM.get(value, 0)


SCHOOL_211 = [
    "苏州大学", "上海财经大学", "中央财经大学", "对外经济贸易大学", "西南财经大学",
    "中南财经政法大学", "北京邮电大学", "北京交通大学", "北京科技大学", "北京化工大学",
    "南京航空航天大学", "南京师范大学", "华东理工大学", "东华大学", "上海大学",
    "暨南大学", "华南师范大学", "华中师范大学", "武汉理工大学", "中国地质大学",
    "中国政法大学", "天津医科大学", "河北工业大学", "太原理工大学", "内蒙古大学",
    "辽宁大学", "大连海事大学", "东北师范大学", "哈尔滨工程大学", "安徽大学",
    "福州大学", "南昌大学", "郑州大学", "湖南师范大学", "广西大学", "四川农业大学",
]


def _level_of(school_name: str | None) -> str | None:
    if not school_name:
        return None
    if school_name in SCHOOL_985:
        return "985"
    if school_name in SCHOOL_211:
        return "211"
    if "大学" in school_name or "学院" in school_name:
        return "普通本科"
    return None


def extract_by_rules(text: str) -> dict:
    """纯正则抽取，无任何外部依赖。抽不到就是抽不到，绝不猜。"""
    text = text or ""
    low = text.lower()
    data: dict = {}

    m = re.search(r"(?:GPA|绩点)[^\d\n]{0,8}([0-9](?:\.[0-9]{1,2})?)(?:\s*[/／]\s*(4\.0|5\.0|100))?", text, re.I)
    if m:
        data["gpa"] = float(m.group(1))
        if m.group(2):
            data["gpa_scale"] = float(m.group(2))

    m = re.search(r"(?:均分|平均分|平均成绩)[^\d\n]{0,8}([0-9]{2,3}(?:\.[0-9]{1,2})?)", text)
    if m:
        data["average_score"] = float(m.group(1))

    m = re.search(r"(?:IELTS|雅思)[^\d\n]{0,8}([4-9](?:\.[05])?)", text, re.I)
    if m:
        data["ielts"] = float(m.group(1))
    m = re.search(r"(?:TOEFL|托福)[^\d\n]{0,8}([0-9]{2,3})", text, re.I)
    if m:
        data["toefl"] = int(m.group(1))
    m = re.search(r"GRE[^\d\n]{0,6}([0-9]{3})", text, re.I)
    if m:
        data["gre"] = int(m.group(1))
    m = re.search(r"GMAT[^\d\n]{0,6}([0-9]{3})", text, re.I)
    if m:
        data["gmat"] = int(m.group(1))

    m = re.search(r"([0-9一二两三四五六七八])\s*段?\s*(?:实习|internship)", text, re.I)
    if m:
        data["internship_count"] = _int(m.group(1))
    m = re.search(r"([0-9一二两三四五六七八])\s*(?:段|个|次)?\s*(?:科研|论文|research|项目)", text, re.I)
    if m:
        data["research_count"] = _int(m.group(1))
    m = re.search(r"([0-9一二两三四五六七八])\s*(?:个|次|项)?\s*(?:竞赛|获奖|奖项|奖学金|award)", text, re.I)
    if m:
        data["award_count"] = _int(m.group(1))

    countries = [name for name, aliases in COUNTRY_ALIASES.items()
                 if any(alias in low for alias in aliases)]
    if countries:
        data["target_country"] = countries

    for degree, aliases in DEGREE_ALIASES.items():
        if any(alias in low for alias in aliases):
            data["target_degree"] = degree
            break

    majors = [name for name, aliases in MAJOR_ALIASES.items()
              if any(alias in low for alias in aliases)]
    if majors:
        data["target_major"] = majors[0]

    # 学生自己的本科专业：先去掉学校名，再找"XX专业"，避免把"苏州大学金融学"整段吃掉
    school_match = re.search(r"([\u4e00-\u9fa5]{2,12}(?:大学|学院))", text)
    if school_match:
        data["school_name"] = school_match.group(1)
        data["school_level"] = _level_of(school_match.group(1))

    major_text = text.replace(data.get("school_name") or "", " ")
    m = re.search(r"([\u4e00-\u9fa5]{2,12})专业", major_text)
    if m:
        data["major"] = m.group(1)
    elif majors:
        data["major"] = majors[0]

    m = re.search(r"([\u4e00-\u9fa5]{2,12}(?:大学|学院))", text)
    if m:
        data["school_name"] = m.group(1)
        data["school_level"] = _level_of(m.group(1))

    m = re.search(r"(?:预算|费用|资金)[^\d]{0,6}([0-9]+(?:\.[0-9]+)?)\s*万", text)
    if m:
        data["budget"] = f"{m.group(1)}万"

    m = re.search(r"(20\d{2})\s*(?:年)?\s*(?:(\d{1,2})\s*月|fall|秋季|春季)?\s*(?:入学|入读|申请)?", text, re.I)
    if m:
        data["intake_year"] = int(m.group(1))
        if m.group(2):
            data["intake_month"] = int(m.group(2))

    m = re.search(r"(大一|大二|大三|大四|研一|研二|研三|应届|已毕业)", text)
    if m:
        data["grade"] = m.group(1)

    return data


def normalize(data: dict) -> StudentBasicInfo:
    """字段清洗：GPA 统一 4.0 制、补风险标签与缺失项。"""
    info = StudentBasicInfo(**{k: v for k, v in data.items()
                               if k in StudentBasicInfo.model_fields})
    if info.gpa is not None:
        info.gpa = gpa_to_4(info.gpa, info.gpa_scale)
        info.gpa_scale = 4.0
    elif info.average_score is not None:
        info.gpa = percent_to_gpa4(info.average_score)

    risks: list[str] = []
    if info.ielts is None and info.toefl is None:
        risks.append("无语言成绩")
    elif info.ielts is not None and info.ielts < 6.5:
        risks.append("语言成绩偏低")
    if info.gpa is not None and info.gpa < 3.0:
        risks.append("GPA偏低")
    if info.internship_count + info.research_count + info.award_count == 0:
        risks.append("无软背景")
    if info.intake_year:
        from datetime import date

        if info.intake_year <= date.today().year:
            risks.append("时间紧张")
    info.risk_tags = list(dict.fromkeys(risks))

    missing: list[str] = []
    if info.gpa is None:
        missing.append("GPA/均分")
    if info.ielts is None and info.toefl is None:
        missing.append("语言成绩（雅思/托福）")
    if not info.target_country:
        missing.append("意向国家")
    if not info.target_major:
        missing.append("目标专业")
    if not info.intake_year:
        missing.append("入学时间")
    if not info.target_degree:
        missing.append("申请学位")
    info.missing_info = missing
    return info


def extract_student(chat_text: str = "", ctx=None, existing: dict | None = None,
                    customer_id: str = "system") -> StudentBasicInfo:
    """主入口：规则 + LLM 双路合并。existing 里的结构化字段优先（人工填过的不覆盖）。"""
    text = chat_text or ""
    base = extract_by_rules(text)

    if ctx is not None and getattr(ctx.llm, "available", False) and text:
        prompt = EXTRACT_STUDENT_PROMPT.format(chat_text=text[:4000])
        llm_data = ctx.llm.json(prompt, fallback=None, tier="big", customer_id=customer_id,
                                system=EXTRACT_STUDENT_SYSTEM)
        if isinstance(llm_data, dict):
            for key, value in llm_data.items():
                if key in StudentBasicInfo.model_fields and value not in (None, "", [], 0):
                    base.setdefault(key, value)

    merged = dict(base)
    for key, value in (existing or {}).items():
        if key in StudentBasicInfo.model_fields and value not in (None, "", [], 0):
            merged[key] = value
    return normalize(merged)


def build_followup(student: StudentBasicInfo, ctx=None, customer_id: str = "system") -> str:
    """缺失信息自动生成追问话术（顾问直接复制发微信）。"""
    if not student.missing_info:
        return ""
    fallback = (
        f"同学你好～为了给你做精准的选校定位，还差几项关键信息：{'、'.join(student.missing_info)}。"
        "你方便发我一下吗？有这些我才能判断冲刺/匹配/保底怎么排，避免方案落空。"
    )
    if ctx is None or not getattr(ctx.llm, "available", False):
        return fallback
    prompt = FOLLOWUP_PROMPT.format(missing="、".join(student.missing_info))
    return ctx.llm.text(prompt, fallback=fallback, tier="small", customer_id=customer_id)
