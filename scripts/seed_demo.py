"""生成演示客户：三个不同阶段、不同背景的学生，让看板一打开就有数据。

用法：
    python scripts/seed_demo.py            # 追加/更新这三个客户
    python scripts/seed_demo.py --reset    # 先清空本地中台再生成
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

from ai_agent_core.base.context import get_context, reset_context  # noqa: E402
from ai_agent_core.base.graph_engine import GraphEngine, build_agents  # noqa: E402
from ai_agent_core.config import RUNTIME_DIR  # noqa: E402
from ai_agent_core.schema.state_schema import CustomerState  # noqa: E402

PROFILES = [
    {
        "customer_id": "demo-001",
        "owner": "advisor1",
        "name": "李同学-南京理工（计算机）",
        "stage": "clue",
        "auto_advance": False,
        "chat": ("学生李同学，南京理工大学计算机科学与技术专业大三，GPA 3.2/4.0，均分 82，"
                 "雅思 6.5，有两段实习，一段科研，想申请英国和香港的计算机硕士，预算 35 万，"
                 "2027 年 9 月入学。家长比较看重 QS 排名，问能不能保录前 50。"),
        "payload": {
            "customer_questions": "你们能不能保录前 50？",
            "experiences": ("1. 2026.07-2026.09 字节跳动 数据分析实习生：用 SQL 清洗 50 万条订单数据，"
                            "搭建 Python 自动化报表，日报产出从 3 小时压缩到 10 分钟。\n"
                            "2. 2025.03-2025.12 南京理工大学实验室科研：基于 XGBoost 的信用违约预测，"
                            "处理 12 万条样本，AUC 从 0.76 提升到 0.84。"),
            "chat_messages": [{"role": "advisor", "text": "放心，我们可以保录前 50。"}],
        },
    },
    {
        "customer_id": "demo-002",
        "owner": "advisor2",
        "name": "王芳-苏州大学（金融）",
        "stage": "material",
        "auto_advance": False,
        "run_school_first": True,
        "chat": ("学生王芳，苏州大学金融学专业大四，GPA 3.6/4.0，均分 88，雅思 7.0，"
                 "三段实习，申请英国金融硕士，预算 40 万，2027 年 9 月入学。"),
        "payload": {
            "experiences": ("1. 2026.06-2026.09 中金公司 投行部实习生：参与 3 个 IPO 项目尽调，"
                            "搭建可比公司估值模型，覆盖 12 家标的。\n"
                            "2. 2025.07-2025.08 招商证券 研究所实习生：撰写行业深度报告 2 篇，"
                            "数据覆盖 300+ 上市公司。"),
            "uploaded_files": [
                {"name": "中英文成绩单", "text": "苏州大学 成绩单 TRANSCRIPT 教务处盖章 GPA 3.6 均分 88"},
                {"name": "存款证明",
                 "text": "中国银行 存款证明 存款金额 400000 元 存入日期 2026-06-01 存期 180 天"},
            ],
        },
    },
    {
        "customer_id": "demo-003",
        "owner": "advisor1",
        "name": "陈同学-港校传媒（全流程）",
        "stage": "clue",
        "auto_advance": True,
        "chat": ("学生陈同学，暨南大学新闻学专业大四，GPA 3.3/4.0，雅思 6.5，两段媒体实习，"
                 "申请香港的传媒硕士，预算 25 万，2027 年 9 月入学。"),
        "payload": {
            "customer_questions": "港三的传媒有机会吗？预算能再低一点吗？",
            "experiences": ("1. 2026.03-2026.08 南方都市报 新媒体实习生：运营账号 3 个，"
                            "产出短视频 40 条，单条最高播放 120 万。\n"
                            "2. 2025.07-2025.09 广东广播电视台 编导助理：参与 2 档栏目策划，"
                            "独立完成 6 期脚本。"),
            "uploaded_files": [
                {"name": "中英文成绩单", "text": "暨南大学 成绩单 TRANSCRIPT 教务处盖章 GPA 3.3 均分 85"},
                {"name": "存款证明",
                 "text": "建设银行 存款证明 存款金额 250000 元 存入日期 2026-08-15 存期 60 天"},
                {"name": "护照", "text": "Passport 姓名 CHEN XIN 护照号 E87654321 有效期至 2032-03-01"},
            ],
            "application_form": {"name_pinyin": "CHEN XIN", "passport_no": "E87654321",
                                 "gpa": 3.3, "program_code": "MA-COMM-2027",
                                 "application_fee_paid": True, "round": "第二轮"},
            "emails": [{"subject": "Interview invitation",
                        "text": "We would like to invite you for a Zoom interview on 2027-02-10."}],
            "referees": [{"email": "prof.li@jnu.edu.cn", "send_link_date": "2026-10-01", "submitted": False}],
            "offer_file": {"text": ("City University of Hong Kong\nProgramme: MA Communication and New Media\n"
                                    "September 2027\n\nConditional Offer\nsubject to achieving an overall "
                                    "average of 85% and IELTS 6.5.\nDeposit HKD 8,000 payable by 2027-03-15.")},
            "fund_data": {"amount": 250000, "deposit_days": 60, "deposit_date": "2026-08-15",
                          "large_inflows": [], "statement_gaps": []},
            "fund_from_parent": True,
            "arrival_date": "2027-09-01",
            "cas_date": "2027-06-15",
            "chat_messages": [{"role": "customer", "text": "能不能保证录取？"}],
        },
    },
    {
        "customer_id": "demo-004",
        "owner": "advisor2",
        "name": "刘同学-新线索（未跟进）",
        "stage": "clue",
        "skip_run": True,
        "chat": "家长咨询：孩子双非本科、GPA 3.0，想读英国商科，预算 30 万，还没考雅思。",
        "payload": {},
    },
]


def build_state(profile: dict) -> CustomerState:
    return CustomerState(
        customer_id=profile["customer_id"],
        customer_name=profile["name"],
        owner=profile.get("owner", ""),
        stage=profile["stage"],
        student_info={"raw_chat": profile["chat"], **profile["payload"]},
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="先清空中台与知识库索引重建")
    args = parser.parse_args()

    if args.reset:
        ctx = get_context()
        counts = ctx.storage.clear_all()
        print(f"[ok] 已清空客户中台：{counts}")
    ctx = get_context()
    if sum(ctx.rag.stats().values()) == 0:
        print("[!] 知识库为空，先跑 python scripts/ingest_seed.py")
        return 1

    engine = GraphEngine(ctx, build_agents(ctx))
    print(f"知识库：{ctx.rag.stats()}\n")

    for profile in PROFILES:
        state = build_state(profile)
        if profile.get("skip_run"):
            # 只建档案不跑 Agent：用来演示"新线索"这一档
            ctx.storage.save_customer(state)
            print(f"[{state.customer_id}] {state.customer_name}  阶段：{state.stage}（仅建档）\n")
            continue
        # 有些人从中间阶段开始（比如已签约），但选校方案必须先有，否则材料 Agent 没有截止日期
        if profile.get("run_school_first"):
            state.stage = "clue"
            state = engine.run(state, auto_advance=False)
            state.stage = profile["stage"]
        state = engine.run(state, auto_advance=profile["auto_advance"])
        out = state.agent_outputs
        school = (out.get("school") or {}).get("result") or {}
        print(f"[{state.customer_id}] {state.customer_name}")
        print(f"    阶段：{state.stage}  执行链：{' → '.join(state.history)}")
        print(f"    选校：冲刺 {len(school.get('sprint_list') or [])} / "
              f"匹配 {len(school.get('match_list') or [])} / 保底 {len(school.get('safe_list') or [])}")
        print(f"    待办 {len(state.task_list)} 条，风险标签 {len(state.risk_tags)} 个")
        if state.errors:
            print(f"    异常：{state.errors}")
        print()

    print(f"完成。中台统计：{ctx.storage.stats()}")
    print(f"刷新浏览器即可看到 {len(PROFILES)} 个客户。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
