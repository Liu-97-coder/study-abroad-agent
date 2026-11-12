"""学生背景抽取 / 咨询纪要 / 追问话术 Prompt。"""

EXTRACT_STUDENT_SYSTEM = "你是留学行业资深顾问助理，只输出结构化 JSON，不做任何解释。"

EXTRACT_STUDENT_PROMPT = """你是留学AI信息抽取专家，严格从用户聊天文本中提取学生背景，禁止编造、禁止脑补。

需要提取字段：
school_level, school_name, major, grade, gpa, gpa_scale, average_score,
ielts, toefl, gre, gmat,
internship_count, research_count, award_count,
target_country, target_degree, target_major, budget, intake_year, intake_month

规则：
1. 没有提到的字段填空字符串或 null，数量类填 0
2. GPA 统一换算为满分 4.0 标准
3. 意向国家、专业输出为数组
4. 自动识别短板写入 risk_tags：无语言、GPA偏低、无软背景、时间紧张
5. 未提供的关键字段写入 missing_info
6. 只返回纯净 JSON，不要解释、不要 markdown

聊天文本：
{chat_text}
"""

CHAT_SUMMARY_PROMPT = """请总结本次留学咨询聊天记录，输出结构化纪要：
1. 客户核心需求
2. 学生背景梳理
3. 家长顾虑 / 痛点
4. 意向国家、专业、预算、时间规划
5. 未解决疑问
6. 本次沟通共识
7. 下一步待办任务

要求：精简、精准、无废话、可直接存档给顾问查看；事实只来自聊天记录，不要补充不存在的信息。

聊天记录：
{chat_text}
"""

FOLLOWUP_PROMPT = """学生档案缺少以下信息：{missing}

请以留学顾问口吻，生成一条微信风格的追问消息：
1. 语气自然礼貌，不超过 150 字
2. 一次只问最关键的 3-4 项，不要列清单式轰炸
3. 说明为什么需要这些信息（用于选校定位）

只输出消息正文。
"""
