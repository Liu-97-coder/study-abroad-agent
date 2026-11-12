"""用一个学生背景，跑一遍选校，把结果翻译成人话。

用法：
    python scripts/try_school.py
    python scripts/try_school.py --chat "学生王芳，苏州大学金融学大四，GPA 3.6，雅思 7.0，申请英国金融硕士"
    python scripts/try_school.py --chat-file my_student.txt
    python scripts/try_school.py --json          # 想看原始结构时加这个
"""
from __future__ import annotations

import argparse
import json
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
from ai_agent_core.phase1.school_agent.school_filter import filter_schools  # noqa: E402
from ai_agent_core.phase1.school_agent.school_score import split_into_three  # noqa: E402
from ai_agent_core.phase1.school_agent.student_extract import extract_student  # noqa: E402

DEMO_CHAT = (
    "学生李同学，南京理工大学计算机科学与技术专业大三，GPA 3.2/4.0，均分 82，"
    "雅思 6.5，有两段实习，一段科研，想申请英国和香港的计算机硕士，预算 35 万，"
    "2027 年 9 月入学。"
)


def show_student(student) -> None:
    print("=" * 62)
    print("① 学生档案（从聊天里自动抽出来的）")
    print("=" * 62)
    print(f"  院校    {student.school_name or '未提供'}（{student.school_level or '未定'}）")
    print(f"  专业    {student.major or '未提供'}")
    print(f"  GPA     {student.gpa if student.gpa is not None else '未提供'} / 4.0")
    lang = f"雅思 {student.ielts}" if student.ielts else (
        f"托福 {student.toefl}" if student.toefl else "未提供")
    print(f"  语言    {lang}")
    print(f"  软背景  实习 {student.internship_count} 段 / 科研 {student.research_count} 项 / "
          f"奖项 {student.award_count} 个")
    print(f"  意向    {'、'.join(student.target_country) or '未定'} · "
          f"{student.target_degree or '未定'} · {student.target_major or '未定'}")
    print(f"  预算    {student.budget or '未提供'}")
    print(f"  入学    {student.intake_year or '未定'} 年")
    print(f"  风险    {'、'.join(student.risk_tags) or '无'}")
    print(f"  还缺    {'、'.join(student.missing_info) or '无（信息齐了）'}")


def show_level(title: str, items: list, note: str) -> None:
    print()
    print(f"【{title} {len(items)} 所】{note}")
    if not items:
        print("    （这一档没有匹配到，建议扩大国家范围或调整预期）")
        return
    print(f"    {'学校':<42}{'专业':<16}{'难度':>5}  {'硬门槛':<26}风险点")
    for idx, item in enumerate(items, 1):
        name = item.school_name if len(item.school_name) <= 38 else item.school_name[:37] + "…"
        major = item.major_name if len(item.major_name) <= 14 else item.major_name[:13] + "…"
        bar = f"{item.gpa_require} / {item.lang_require}"
        print(f"  {idx}. {name:<40}{major:<16}{item.match_score:>5}  {bar:<26}{item.risk_point}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chat", default="")
    parser.add_argument("--chat-file", default="")
    parser.add_argument("--json", action="store_true", help="打印原始 JSON")
    args = parser.parse_args()

    chat = args.chat
    if args.chat_file:
        chat = Path(args.chat_file).read_text(encoding="utf-8")
    if not chat:
        chat = DEMO_CHAT
        print("（没有传 --chat，用内置的示例学生）\n")

    ctx = get_context()
    if sum(ctx.rag.stats().values()) == 0:
        print("[!] 知识库是空的，先跑：python scripts\\ingest_seed.py")
        return 1

    print(f"输入：{chat[:60]}{'…' if len(chat) > 60 else ''}\n")
    student = extract_student(chat, ctx=ctx, customer_id="try-001")
    show_student(student)

    filtered = filter_schools(ctx.rag, student)
    buckets = split_into_three(filtered.candidates, student)
    total = sum(len(v) for v in buckets.values())

    print()
    print("=" * 62)
    print(f"② 三档选校（共 {total} 所）— 难度分越高 = 越难录")
    print("=" * 62)
    show_level("冲刺", buckets["冲刺"], "（差一点，值得试，但别全押这里）")
    show_level("匹配", buckets["匹配"], "（主战场，建议 4-6 所）")
    show_level("保底", buckets["保底"], "（确保有学上）")

    if filtered.dropped:
        print(f"\n【被剔除 {len(filtered.dropped)} 所】")
        for row in filtered.dropped[:5]:
            print(f"    {row['school_name']} {row['major_name']}：{row['reason']}")

    sources = [c["source_id"] for c in filtered.candidates]
    print(f"\n【溯源】{len(sources)} 条结果都带来源 ID（防幻觉）：{', '.join(sources[:6])} …")

    first = (buckets["冲刺"] or buckets["匹配"] or buckets["保底"])
    if first:
        item = first[0]
        print(f"\n【打分拆解】以「{item.school_name} {item.major_name}」为例，总分 {item.match_score}：")
        for key, value in item.score_detail.items():
            print(f"    {key:<8} 贡献 {value} 分")

    if args.json:
        print("\n" + json.dumps({"student": student.model_dump(),
                                 "buckets": {k: [i.model_dump() for i in v]
                                             for k, v in buckets.items()}},
                                ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
