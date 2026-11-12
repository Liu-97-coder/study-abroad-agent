"""院校押金 / CAS / 语言班政策匹配（Offer Agent 步骤 2）。

Offer 上写的时间和学校官网 RAG 库里的时间经常不一致（Offer 是模板，官网是政策）。
不一致不是错，但必须标出来 —— 这就是"政策冲突检测"。
"""
from __future__ import annotations

from ...schema.offer_schema import OfferPolicyInfo
from ...utils.date_utils import days_until, parse_date


def match_policy(school_name: str, major: str, ctx) -> tuple[OfferPolicyInfo, list[str]]:
    sources: list[str] = []
    chunks = ctx.rag.search("school", f"{school_name} {major} 押金 退费 CAS 换无条件 截止",
                            top_k=10, rerank_top=3)
    if not chunks:
        return OfferPolicyInfo(
            deposit_refund_rule="院校库无该政策数据，需顾问人工核对官网",
            policy_conflict="无 RAG 数据支撑，禁止向客户承诺押金可退"), sources

    meta = dict(chunks[0].metadata)
    sources = [c.source_info.get("source_id", "") for c in chunks]
    policy = OfferPolicyInfo(
        deposit_amount=str(meta.get("deposit", "") or ""),
        deposit_refund_rule=str(meta.get("deposit_refund", "") or "未注明"),
        cas_material_list=["Offer 原件", "押金缴纳凭证", "护照扫描件", "毕业证/学位证",
                           "完整成绩单", "语言成绩单"],
        unconditional_deadline=str(meta.get("uncon_deadline", "") or meta.get("unconditional_deadline", "") or ""),
        language_course_deadline=str(meta.get("language_course_deadline", "") or ""),
    )
    return policy, sources


def detect_conflict(offer_deadline: str, policy: OfferPolicyInfo) -> str:
    """Offer 上的截止与官网政策截止是否一致。"""
    d1, d2 = parse_date(offer_deadline), parse_date(policy.unconditional_deadline)
    if not d1 or not d2:
        return ""
    if d1 != d2:
        return (f"政策冲突：Offer 标注 {d1.isoformat()}，院校库记录 {d2.isoformat()}，"
                "以官网最新公告为准并留痕")
    return ""


def refund_risk(policy: OfferPolicyInfo) -> str:
    text = (policy.deposit_refund_rule or "").lower()
    if any(k in text for k in ("不退", "non-refundable", "no refund")):
        return "高"
    if any(k in text for k in ("部分", "partial")):
        return "中"
    return "低"


def urgency(policy: OfferPolicyInfo) -> str:
    left = days_until(policy.unconditional_deadline)
    if left is None:
        return ""
    if left <= 15:
        return f"距换无条件截止仅 {left} 天，需加急"
    if left <= 30:
        return f"距换无条件截止 {left} 天，进入冲刺期"
    return ""
