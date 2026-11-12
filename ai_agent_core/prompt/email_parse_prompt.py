"""二期：院校邮件意图识别 Prompt。"""

MAIL_INTENT_PARSE_PROMPT = """读取海外院校发来的原始邮件文本，识别邮件意图，仅分为五类：
补件通知、面试邀请、押金提醒、Offer发放、拒信WL

抽取关键信息：截止日期、需要补充的材料、面试时间、押金金额、CAS 相关要求。

规则：只提取原文存在的信息，禁止脑补时间、材料；模糊文字标记识别风险。
输出严格 JSON：{{"mail_intent": "...", "deadline": "YYYY-MM-DD 或 null", "need_supplement": [], "extra_notice": "...", "confidence": 0-1}}

邮件文本：
{mail_text}
"""
