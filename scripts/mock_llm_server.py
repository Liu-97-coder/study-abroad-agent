"""OpenAI 兼容的本地假模型服务（仅用于验证 LLM 接入链路，不产生费用）。

作用：不花钱就能验证「HTTP 调用 → JSON 解析 → 缓存 → 重试 → 降级」这条链路，
以及"配了真实模型后，Agent 的输出会变成什么样"。

用法：
    python scripts/mock_llm_server.py --port 8199
    # 另一个终端：
    $env:LLM_PROVIDER="openai"; $env:LLM_BASE_URL="http://127.0.0.1:8199/v1"
    $env:LLM_API_KEY="test"; $env:LLM_MODEL_BIG="mock-gpt"

它实现两个接口：
    POST /v1/chat/completions
    POST /v1/embeddings
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Mock LLM Server")

PS_SAMPLE = """My interest in computer science began in a university database course, where I built a
small campus second-hand trading platform. Watching 300 students use it daily convinced me that
data systems are not abstract: they change how people coordinate.

At Nanjing University of Science and Technology I took algorithms, database systems and machine
learning, maintaining a 3.2/4.0 GPA. In the credit-default project, I processed 120,000 samples
with XGBoost and lifted AUC from 0.76 to 0.84 by engineering repayment-window features.

During my internship at ByteDance I cleaned 500,000 order records with SQL and automated reporting
that cut daily report time from three hours to ten minutes. This taught me to measure impact in
minutes saved, not lines of code.

Manchester's Advanced Computer Science programme, particularly its Data Engineering and
Scalable Systems modules, is exactly where I want to deepen distributed data processing.
In five years I aim to lead data infrastructure for a fintech platform serving underbanked users.

This is a mock-generated paragraph used only to verify the LLM wiring end to end."""

CV_SAMPLE = """# LI MING
*Target: MSc Advanced Computer Science*

## EDUCATION
- Nanjing University of Science and Technology — Computer Science, GPA 3.2/4.0

## RESEARCH & PROJECTS
- Credit Default Prediction (XGBoost, 120k samples): AUC 0.76 → 0.84
- Campus Trading Platform (300 daily users)

## INTERNSHIP EXPERIENCE
- ByteDance, Data Analyst Intern: cleaned 500k orders, report time 3h → 10min
- Bank of Jiangsu, Risk Tech Intern: 120 test cases, 8 rule defects found

## SKILLS
Python, SQL, XGBoost, Tableau"""


class ChatRequest(BaseModel):
    model: str = "mock-gpt"
    messages: list[dict] = []
    temperature: float = 0.3
    response_format: dict | None = None


class EmbedRequest(BaseModel):
    model: str = "mock-embed"
    input: str | list[str] = ""


def _hash_vec(text: str, dim: int = 64) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    vec = [((b / 255.0) - 0.5) for b in digest]
    vec = (vec * ((dim // len(vec)) + 1))[:dim]
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


@app.post("/v1/chat/completions")
def chat(req: ChatRequest):
    prompt = "\n".join(m.get("content", "") for m in req.messages)
    wants_json = bool(req.response_format) or "JSON" in prompt or "json" in prompt

    if wants_json:
        content = json.dumps(_fake_json(prompt), ensure_ascii=False)
    elif "Personal Statement" in prompt or "personal statement" in prompt:
        content = PS_SAMPLE
    elif "CV" in prompt or "resume" in prompt.lower():
        content = CV_SAMPLE
    else:
        content = ("【mock 模型输出】已收到请求。关键词："
                   + ", ".join(sorted(set(prompt.split()[:20])))[:200])

    return {
        "id": "chatcmpl-mock",
        "object": "chat.completion",
        "model": req.model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": len(prompt) // 4, "completion_tokens": len(content) // 4,
                  "total_tokens": (len(prompt) + len(content)) // 4},
    }


def _fake_json(prompt: str) -> dict:
    """按调用方意图返回结构合理的假 JSON，用来验证解析与字段映射。"""
    low = prompt.lower()
    if "personal statement" in low or "文书质检" in prompt or "quality" in low:
        return {"total": 82, "dimensions": {"真实匹配度": 85, "专业匹配度": 80,
                                            "模板化程度": 20, "空话冗余度": 15,
                                            "逻辑连贯性": 88, "语法地道性": 84},
                "comments": ["结构完整，经历绑定具体"], "suggestions": ["第二段可再补一个量化结果"]}
    if "学生背景" in prompt or "gpa" in low or "抽取" in prompt:
        return {"school_level": "985", "school_name": "南京理工大学", "major": "计算机科学与技术",
                "gpa": 3.2, "gpa_scale": 4.0, "average_score": 82,
                "ielts": 6.5, "toefl": None, "gre": None, "gmat": None,
                "internship_count": 2, "research_count": 1, "award_count": 0,
                "target_country": ["英国", "香港"], "target_degree": "硕士",
                "target_major": "计算机", "budget": "35万", "intake_year": 2027,
                "intake_month": 9, "risk_tags": ["无软背景"], "missing_info": []}
    if "offer" in low or "条件" in prompt:
        return {"is_conditional": True, "school_name": "University of Manchester",
                "major": "Advanced Computer Science", "intake": "September 2027",
                "conditions": [{"cond_type": "均分", "require_value": "85%"},
                               {"cond_type": "语言", "require_value": "IELTS 7.0"}]}
    if "资金" in prompt or "visa" in low:
        return [{"risk_tag": "大额临存", "risk_level": "高", "reason": "近 5 天入账占比 50%",
                 "fix_plan": "补充资金来源证明"}]
    if "邮件" in prompt or "mail" in low:
        return {"mail_intent": "补件通知", "deadline": "2027-01-15",
                "need_supplement": ["最终成绩单"], "extra_notice": "", "confidence": 0.9}
    return {"ok": True, "note": "mock json"}


@app.post("/v1/embeddings")
def embeddings(req: EmbedRequest):
    texts = [req.input] if isinstance(req.input, str) else list(req.input)
    return {
        "object": "list",
        "model": req.model,
        "data": [{"object": "embedding", "index": i, "embedding": _hash_vec(t)}
                 for i, t in enumerate(texts)],
        "usage": {"prompt_tokens": sum(len(t) // 4 for t in texts)},
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "mock-llm"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8199)
    args = parser.parse_args()
    print(f"Mock LLM 服务：http://127.0.0.1:{args.port}/v1  （Ctrl+C 停止）")
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
