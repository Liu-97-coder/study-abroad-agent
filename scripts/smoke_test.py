"""端到端自测：一个客户从线索走到签证，检查七个 Agent 的产出。

用法：
    python scripts/smoke_test.py

它同时是一份「活文档」：把 state.student_info 里的输入数据换成真实客户，
就能看到每个 Agent 实际吐什么结构。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

from ai_agent_core.base.context import get_context  # noqa: E402
from ai_agent_core.base.graph_engine import GraphEngine, build_agents  # noqa: E402
from ai_agent_core.schema.state_schema import CustomerState  # noqa: E402

CHAT_TEXT = (
    "学生李同学，南京理工大学计算机科学与技术专业大三，GPA 3.2/4.0，均分 82，"
    "雅思 6.5，有两段实习，一段科研，想申请英国和香港的计算机硕士，预算 35 万，"
    "2027 年 9 月入学。家长比较看重 QS 排名，问能不能保录前 50。"
)

EXPERIENCES = (
    "1. 2026.07-2026.09 字节跳动 数据分析实习生：负责本地生活商户数据看板，"
    "用 SQL 清洗 50 万条订单数据，搭建 Python 自动化报表，日报产出时间从 3 小时压缩到 10 分钟。\n"
    "2. 2025.07-2025.09 江苏银行 金融科技部实习生：参与风控规则测试，编写 120 条测试用例，"
    "发现 8 个规则漏洞，覆盖 3 个核心风控场景。\n"
    "3. 2025.03-2025.12 南京理工大学实验室科研：基于 XGBoost 的信用违约预测，"
    "处理 12 万条样本，AUC 从 0.76 提升到 0.84。\n"
    "4. 2025.11 全国大学生数学建模竞赛 省二等奖。"
)

OFFER_TEXT = (
    "University of Manchester\n"
    "Programme: Advanced Computer Science\n"
    "September 2027\n\n"
    "Conditional Offer\n"
    "This offer is subject to achieving an overall average of 85% and IELTS 7.0 "
    "with no band below 6.5. You must also provide your degree certificate.\n"
    "Tuition deposit: GBP 1,000 payable by 2027-03-31.\n"
    "Please respond to this offer by 2027-02-15."
)

FUND_DATA = {
    "amount": 300000,
    "deposit_days": 22,
    "deposit_date": "2026-10-20",
    "large_inflows": [{"amount": 150000, "days_ago": 5}],
    "statement_gaps": [75],
}


def build_demo_state() -> CustomerState:
    return CustomerState(
        customer_id="demo-001",
        customer_name="李同学-南京理工",
        stage="clue",
        student_info={
            "raw_chat": CHAT_TEXT,
            "customer_questions": "你们能不能保录前 50？",
            "experiences": EXPERIENCES,
            "uploaded_files": [
                {"name": "中英文成绩单",
                 "text": "南京理工大学 学生成绩单 TRANSCRIPT 教务处盖章 "
                         "GPA 3.2 均分 82 计算机科学与技术"},
                {"name": "存款证明",
                 "text": "中国银行 存款证明 存款金额 300000 元 存入日期 2026-10-20 存期 30 天"},
                {"name": "护照",
                 "text": "Passport 姓名 LI MING 护照号 E12345678 有效期至 2031-05-01"},
            ],
            "application_form": {
                "name_pinyin": "LI MING",
                "passport_no": "E12345679",
                "gpa": 3.3,
                "program_code": "MSC-CS-2027",
                "application_fee_paid": True,
                "round": "第一轮",
            },
            "emails": [
                {"subject": "Missing documents for your application",
                 "text": "We require an additional document: your final transcript. "
                         "Please upload before 2027-01-15."},
                {"subject": "Interview invitation",
                 "text": "We would like to invite you for a Kira video assessment. "
                         "Please complete it before 2027-01-10."},
            ],
            "referees": [
                {"email": "prof.zhang@njust.edu.cn", "send_link_date": "2026-10-20",
                 "submitted": False},
            ],
            "offer_file": {"text": OFFER_TEXT},
            "fund_data": FUND_DATA,
            "fund_from_parent": True,
            "arrival_date": "2027-09-01",
            "cas_date": "2027-06-01",
            "chat_messages": [
                {"role": "advisor", "text": "放心，我们可以保录前 50，也能保过雅思。"},
                {"role": "customer", "text": "真的吗？那太好了。"},
            ],
        },
    )


def main() -> int:
    ctx = get_context()
    if sum(ctx.rag.stats().values()) == 0:
        print("[!] 知识库为空，先运行 python scripts/ingest_seed.py")
        return 1

    state = build_demo_state()
    engine = GraphEngine(ctx, build_agents(ctx))
    state = engine.run(state, auto_advance=True)

    school = (state.agent_outputs.get("school") or {})
    result = school.get("result") or {}
    document = state.agent_outputs.get("document") or {}
    material = state.agent_outputs.get("material") or {}
    application = state.agent_outputs.get("application") or {}
    offer = state.agent_outputs.get("offer") or {}
    visa = state.agent_outputs.get("visa") or {}
    risk = state.agent_outputs.get("risk") or {}

    print("=" * 66)
    print(f"客户：{state.customer_name}  阶段：{state.stage}  Trace：{state.trace_id}")
    print(f"执行链：{' → '.join(state.history)}")
    print("=" * 66)

    print("\n【1】选校 Agent")
    print(f"  学生档案：GPA {state.student_info.get('gpa')} / 雅思 {state.student_info.get('ielts')} "
          f"/ 国家 {state.student_info.get('target_country')}")
    print(f"  风险标签：{'、'.join(state.student_info.get('risk_tags') or []) or '无'}")
    for level, key in (("冲刺", "sprint_list"), ("匹配", "match_list"), ("保底", "safe_list")):
        items = result.get(key) or []
        names = "、".join(f"{i['school_name']}({i['match_score']})" for i in items[:4])
        print(f"  {level} {len(items)} 所：{names or '无'}")
    print(f"  剔除：{len(result.get('filtered_out') or [])} 所（硬门槛/已截止/无溯源）")
    print(f"  溯源 source_id：{len(result.get('sources') or [])} 条")

    print("\n【2】文书 Agent")
    q = document.get("quality") or {}
    print(f"  经历条目：{document.get('experience_count')} 条")
    print(f"  质检总分：{q.get('total')}（{q.get('source')}） 维度：{q.get('dimensions')}")
    print(f"  版本存档：{list((document.get('versions') or {}).keys())}")

    print("\n【3】材料 Agent")
    print(f"  清单 {len(material.get('material_list') or [])} 项，缺失："
          f"{'、'.join(material.get('missing_materials') or [])[:80]}")
    print(f"  高危风险 {len([r for r in material.get('all_risk') or [] if r.get('risk_level') == '高'])} 条")

    print("\n【4】网申 Agent")
    print(f"  表单错误：{[e['field_name'] for e in application.get('form_error_list') or []]}")
    print(f"  邮件意图：{[m['mail_intent'] for m in application.get('mail_info_list') or []]}")
    print(f"  截止预警：{len(application.get('deadline_warn_list') or [])} 条")

    print("\n【5】Offer Agent")
    print(f"  {offer.get('school_name')} / {offer.get('major')} 条件式：{offer.get('is_conditional')}")
    for cond in offer.get("cond_list") or []:
        print(f"    - {cond['cond_type']}：{cond['require_value']} → {cond['reach_risk']}"
              f"（{cond.get('gap')}）")

    print("\n【6】签证 Agent")
    print(f"  国家 {visa.get('target_country')} 资金 {visa.get('fund_total')} 元 "
          f"整体风险 {visa.get('overall_risk')}")
    for risk_item in visa.get("fund_risk_list") or []:
        print(f"    - [{risk_item['risk_level']}] {risk_item['risk_tag']}：{risk_item['reason'][:50]}")

    print("\n【7】风控 Agent")
    pred = risk.get("prediction") or {}
    print(f"  风险分 {pred.get('score')}（{pred.get('level')}）标签 {pred.get('tags')}")
    print(f"  合规工单 {len(risk.get('workorders') or [])} 条")

    print("\n【汇总】")
    print(f"  风险标签：{'、'.join(state.risk_tags) or '无'}")
    print(f"  待办 {len(state.task_list)} 条，其中紧急 "
          f"{len([t for t in state.task_list if t.get('level') == '紧急'])} 条")
    print(f"  错误：{state.errors or '无'}")
    print(f"  LLM 调用：{ctx.llm.stats.snapshot()}")
    print(f"  日志：{ctx.logger.stats()}")
    print(f"  中台：{ctx.storage.stats()}")

    # ---------------- 断言（回归保护） ----------------
    checks = [
        ("选校有产出", bool(result.get("sprint_list") or result.get("match_list"))),
        ("三档至少两档非空", sum(bool(result.get(k)) for k in
                            ("sprint_list", "match_list", "safe_list")) >= 2),
        ("每条选校结果都带 source_id",
         all(i.get("source_id") for i in
             (result.get("sprint_list") or []) + (result.get("match_list") or [])
             + (result.get("safe_list") or []))),
        ("文书有质检分", float(document.get("quality", {}).get("total") or 0) > 0),
        ("文书版本已存档", bool(document.get("versions"))),
        ("材料清单已生成", bool(material.get("material_list"))),
        ("网申护照号错误被拦截",
         any(e.get("field_name") == "护照号" for e in application.get("form_error_list") or [])),
        ("Offer 条件被解析", len(offer.get("cond_list") or []) >= 2),
        ("签证资金风险被识别", bool(visa.get("fund_risk_list"))),
        ("违规话术被拦截", bool(risk.get("workorders"))),
        ("产生了待办", len(state.task_list) > 0),
        ("全链路无异常", not state.errors),
    ]
    print("\n【断言】")
    failed = 0
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
        failed += 0 if ok else 1
    print("\n" + ("全部通过 ✅" if failed == 0 else f"{failed} 项未通过 ❌"))
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
