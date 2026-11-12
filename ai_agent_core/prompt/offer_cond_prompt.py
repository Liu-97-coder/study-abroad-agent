"""二期：Cond Offer 条件抽取与达标风险测算 Prompt。"""

OCR_OFFER_COND_PROMPT = """基于 Offer 文件 OCR 文本，精准提取全部录取约束条件：
均分要求、雅思/托福、GRE/GMAT、毕业证提交、语言班要求、押金金额与截止日。

区分无条件 Offer 与有条件 Offer，每条条件清晰拆分，禁止合并模糊描述。
输出严格 JSON：{{"is_conditional": true, "school_name": "", "major": "", "intake": "", "conditions": [{{"cond_type": "", "require_value": ""}}]}}

OCR 文本：
{raw_text}
"""

COND_RISK_CAL_PROMPT = """输入学生当前成绩、Offer 硬性要求、剩余学习周期，计算达标风险：

1. 低风险：现有成绩轻松满足
2. 中风险：小幅刷分/重修即可达标
3. 高风险：差距极大，基本无法完成

同时给出可执行提升方案：刷语言、重修课程、加申保底院校。
所有测算逻辑基于真实分数，不主观臆断。
输出严格 JSON 数组：[{{"cond_type": "", "reach_risk": "低|中|高", "improve_suggest": ""}}]

学生当前：{student}
Offer 条件：{conditions}
"""
