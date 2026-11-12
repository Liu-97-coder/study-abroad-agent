"""把真实 LLM 的 Key 写进 .env，并当场验证；失败自动回滚。

用法：
    python scripts/set_llm_key.py --key sk-xxxxxxxx
    python scripts/set_llm_key.py --key sk-xxx --provider deepseek --model deepseek-chat
    python scripts/set_llm_key.py --show          # 只看当前配置（Key 打码）
    python scripts/set_llm_key.py --restore       # 回滚到上一次备份
    python scripts/set_llm_key.py --key sk-xxx --no-verify   # 不验证直接写

设计要点：
- Key 只写本地 .env（已在 .gitignore），终端输出一律打码
- 写之前备份 .env → .env.bak，验证失败自动还原，不会把你搞成"半配好"
- 验证会真发一次请求：能区分 401（Key 错）、402/余额不足、超时（网络）
"""
from __future__ import annotations

import argparse
import dataclasses
import shutil
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
from ai_agent_core.config import PROJECT_DIR, settings  # noqa: E402

ENV_FILE = PROJECT_DIR / ".env"
BACKUP = PROJECT_DIR / ".env.bak"
MANAGED = ["LLM_PROVIDER", "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL_BIG", "LLM_MODEL_SMALL"]

PRESETS = {
    "deepseek": {"base": "https://api.deepseek.com/v1", "model": "deepseek-chat"},
    "openai": {"base": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
    "ollama": {"base": "http://127.0.0.1:11434/v1", "model": "qwen2.5:3b"},
}


def mask(key: str) -> str:
    if not key:
        return "(空)"
    if len(key) <= 10:
        return key[:2] + "***"
    return f"{key[:6]}…{key[-4:]}（{len(key)} 位）"


def read_env() -> dict[str, str]:
    data = {}
    if not ENV_FILE.exists():
        return data
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            data[k.strip()] = v.strip()
    return data


def write_env(values: dict[str, str]) -> None:
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    remaining = dict(values)
    out = []
    for line in lines:
        if "=" in line and not line.strip().startswith("#"):
            key = line.split("=", 1)[0].strip()
            if key in remaining:
                out.append(f"{key}={remaining.pop(key)}")
                continue
        out.append(line)
    for key, value in remaining.items():
        out.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


def verify(provider: str, base: str, key: str, model: str) -> tuple[bool, str]:
    cfg = dataclasses.replace(settings, llm_provider=provider, llm_base_url=base,
                              llm_api_key=key, llm_model_big=model, llm_model_small=model,
                              llm_timeout=30, llm_max_retry=0, log_dir=PROJECT_DIR / "logs")
    try:
        ctx = AgentContext.build(cfg)
    except Exception as exc:  # noqa: BLE001
        return False, f"初始化失败：{exc}"

    health = ctx.llm.health_check()
    if not health.get("ok"):
        return False, str(health.get("detail") or "健康检查失败")

    answer = ctx.llm.text("用一句中文回答：你能正常工作吗？", fallback="")
    if not answer:
        return False, "模型返回空内容"
    return True, f"{health.get('latency_ms')}ms · {answer[:60]}"


def show() -> int:
    env = read_env()
    print("当前 .env 配置：")
    for key in MANAGED:
        value = env.get(key, "")
        print(f"  {key:16} = {mask(value) if key == 'LLM_API_KEY' else (value or '(未设置)')}")
    live = settings.llm_enabled
    print(f"\n  llm_enabled = {live}（{'已接真实模型' if live else '离线 mock 模式'}）")
    return 0


def restore() -> int:
    if not BACKUP.exists():
        print("没有可回滚的备份（.env.bak 不存在）")
        return 1
    shutil.copy(BACKUP, ENV_FILE)
    print("已回滚 .env ← .env.bak，重启服务生效")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--key", default="")
    parser.add_argument("--provider", default="deepseek", choices=list(PRESETS))
    parser.add_argument("--base", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--restore", action="store_true")
    parser.add_argument("--no-verify", action="store_true")
    args = parser.parse_args()

    if args.show:
        return show()
    if args.restore:
        return restore()

    key = (args.key or "").strip()
    if not key:
        print("缺少 --key。示例：python scripts/set_llm_key.py --key sk-xxxxxxxx")
        return 2

    preset = PRESETS[args.provider]
    base = args.base or preset["base"]
    model = args.model or preset["model"]

    print(f"① 目标：{args.provider} / {model} / {base}")
    print(f"   Key ：{mask(key)}")

    if ENV_FILE.exists():
        shutil.copy(ENV_FILE, BACKUP)
        print(f"   已备份 .env → .env.bak")

    write_env({"LLM_PROVIDER": args.provider, "LLM_API_KEY": key,
               "LLM_BASE_URL": base, "LLM_MODEL_BIG": model, "LLM_MODEL_SMALL": model})
    print("② 已写入 .env")

    if args.no_verify:
        print("③ 跳过验证（--no-verify）。重启服务后生效。")
        return 0

    print("③ 真发一次请求验证…")
    ok, detail = verify(args.provider, base, key, model)
    if ok:
        print(f"   [OK] {detail}")
        print("\n完成。重启服务生效：")
        print("   powershell -ExecutionPolicy Bypass -File scripts\\dev.ps1")
        print("   或用 停止服务.bat 后再 启动服务.bat")
        return 0

    shutil.copy(BACKUP, ENV_FILE)
    print(f"   [FAIL] {detail}")
    print("   已自动回滚 .env（仍是原来的配置）")
    hint = ""
    low = detail.lower()
    if "401" in low or "unauthorized" in low or "invalid" in low:
        hint = "Key 不正确或已被删除，去 platform.deepseek.com 重新创建"
    elif "402" in low or "balance" in low or "insufficient" in low:
        hint = "账户余额不足，去开放平台充值（10 元即可）"
    elif "timeout" in low or "timed out" in low or "urlopen" in low:
        hint = "网络不通：检查代理/防火墙，或换 --base 为可访问的网关"
    print(f"   建议：{hint or '看上面的错误信息'}")

    if not ENV_FILE.read_text(encoding="utf-8").count("LLM_PROVIDER=mock"):
        print("   注意：当前 .env 的 LLM_PROVIDER 不是 mock，请确认回滚是否成功")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
