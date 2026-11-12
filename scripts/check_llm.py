"""真实 LLM 接入自检：确认「HTTP → JSON 解析 → 缓存 → 业务链路」都通。

用法（先用假模型服务验证，零成本）：
    python scripts/mock_llm_server.py --port 8199        # 终端 A
    python scripts/check_llm.py --base http://127.0.0.1:8199/v1   # 终端 B

换成 DeepSeek（真花钱）：
    python scripts/check_llm.py --provider deepseek --key sk-xxxx
"""
from __future__ import annotations

import argparse
import dataclasses
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

from ai_agent_core.base.context import AgentContext  # noqa: E402
from ai_agent_core.config import settings  # noqa: E402
from ai_agent_core.phase1.doc_agent.experience_parse import parse_experiences  # noqa: E402
from ai_agent_core.phase1.doc_agent.ps_generator import generate_ps  # noqa: E402
from ai_agent_core.phase1.school_agent.student_extract import extract_student  # noqa: E402

CHAT = ("学生李同学，南京理工大学计算机科学与技术专业大三，GPA 3.2/4.0，均分 82，雅思 6.5，"
        "有两段实习，一段科研，想申请英国和香港的计算机硕士，预算 35 万，2027 年 9 月入学。")
EXPS = ("1. 2026.07-2026.09 字节跳动 数据分析实习生：用 SQL 清洗 50 万条订单数据，"
        "自动化报表把日报从 3 小时压到 10 分钟。\n"
        "2. 2025.03-2025.12 实验室科研：XGBoost 信用违约预测，12 万样本，AUC 0.76→0.84。")


DEFAULT_PRESETS = {
    "deepseek": ("https://api.deepseek.com/v1", "deepseek-chat"),
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini"),
    "ollama": ("http://127.0.0.1:11434/v1", "qwen2.5:3b"),
    "openai_compatible": ("http://127.0.0.1:8199/v1", "mock-gpt"),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default=settings.llm_provider)
    parser.add_argument("--base", default="")
    parser.add_argument("--key", default="")
    parser.add_argument("--model", default="")
    args = parser.parse_args()

    base, model = DEFAULT_PRESETS.get(args.provider, DEFAULT_PRESETS["openai_compatible"])
    base = args.base or base
    model = args.model or model
    key = args.key or settings.llm_api_key

    if not key and args.provider != "ollama":
        print("缺少 Key：用 --key sk-xxx，或先跑 scripts/set_llm_key.py 写进 .env")
        return 2

    cfg = dataclasses.replace(
        settings, llm_provider=args.provider, llm_base_url=base,
        llm_api_key=key, llm_model_big=model, llm_model_small=model,
        llm_timeout=30, llm_max_retry=0,
    )
    ctx = AgentContext.build(cfg)

    results: list[tuple[str, bool, str]] = []

    def check(name, fn):
        try:
            ok, detail = fn()
        except Exception as exc:  # noqa: BLE001
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        results.append((name, ok, detail))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}  {detail}")

    print(f"目标：{args.provider} @ {base}（{model}）\n")
    print("① 连接与调度")
    check("llm.available 为 True", lambda: (ctx.llm.available, f"provider={cfg.llm_provider}"))

    def _health():
        h = ctx.llm.health_check()
        return h["ok"], f"{h.get('latency_ms')}ms / {h.get('model')}"

    check("健康检查（真实发一次请求）", _health)
    check("自由文本生成", lambda: (bool(ctx.llm.text("用一句话说明留学文书要点", fallback="")), "已返回"))

    def _json():
        prompt = ('只返回 JSON，不要任何解释：'
                  '{"gpa": 3.2, "ielts": 6.5, "target_country": ["英国"], "target_major": "计算机"}')
        data = ctx.llm.json(prompt, fallback=None)
        ok = isinstance(data, dict) and {"gpa", "ielts"} <= set(data)
        return ok, f"keys={list(data.keys())[:5] if isinstance(data, dict) else data}"

    check("JSON 模式（结构化输出）", _json)

    print("\n② 缓存与成本")
    before = ctx.llm.stats.cache_hits
    ctx.llm.text("同一句话", fallback="")
    ctx.llm.text("同一句话", fallback="")
    check("相同 Prompt 命中缓存", lambda: (ctx.llm.stats.cache_hits > before,
                                          f"hits={ctx.llm.stats.cache_hits}"))
    check("token 计量已记录", lambda: (ctx.llm.stats.prompt_tokens > 0,
                                      f"prompt={ctx.llm.stats.prompt_tokens} completion={ctx.llm.stats.completion_tokens}"))

    print("\n③ 业务链路（模型真的改写了输出）")
    def _extract():
        student = extract_student(CHAT, ctx=ctx, customer_id="llm-check")
        return student.gpa == 3.2 and student.ielts == 6.5, f"gpa={student.gpa} ielts={student.ielts}"

    check("学生背景抽取走模型", _extract)

    def _ps():
        student = extract_student(CHAT, ctx=ctx, customer_id="llm-check")
        exps = parse_experiences(EXPS)
        data = generate_ps(student, exps, ctx, "llm-check")
        text = data.get("content", "")
        english = sum(1 for ch in text if ch.isascii() and ch.isalpha()) > len(text) * 0.5
        return data.get("source") == "llm" or english, f"source={data.get('source')} 长度={len(text)} 英文为主={english}"

    check("PS 由模型生成（source=llm）", _ps)

    failed = [r for r in results if not r[1]]
    print(f"\n{'全部通过 ✅' if not failed else f'{len(failed)} 项未通过 ❌'}")
    print(f"调用统计：{ctx.llm.stats.snapshot()}")
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
