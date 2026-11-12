"""LLM 统一调度池（基座任务 3.6）。

四个能力：
1. 大小模型分层（tier="big"/"small"）
2. 结果缓存（相同 Prompt 1 小时内不重复花钱）
3. 限流（单客户同时最多 N 个调用）
4. 超时重试 + 失败兜底（返回 fallback，绝不抛异常打断流程）

mock 模式下不发起任何网络请求，直接返回调用方给的 fallback（规则/模板产物），
所以整套系统零成本、离线可跑；配好 API Key 后自动切到真实模型。
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request

from ..config import Settings, settings as default_settings
from ..utils.cache_utils import TTLCache, make_key
from ..utils.json_utils import loads_lenient
from ..utils.text_clean import truncate


class LLMStats:
    def __init__(self) -> None:
        self.calls = 0
        self.cache_hits = 0
        self.failures = 0
        self.prompt_chars = 0
        self.latency_ms = 0.0
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def snapshot(self) -> dict:
        return {
            "calls": self.calls,
            "cache_hits": self.cache_hits,
            "failures": self.failures,
            "prompt_chars": self.prompt_chars,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "avg_latency_ms": round(self.latency_ms / self.calls, 1) if self.calls else 0,
            "cache": getattr(self, "_cache", {}),
        }


class LLMDispatcher:
    def __init__(self, cfg: Settings | None = None, logger=None):
        self.cfg = cfg or default_settings
        self.logger = logger
        self.cache = TTLCache(ttl=self.cfg.llm_cache_ttl)
        self.stats = LLMStats()
        self.last_error = ""
        self._sem_lock = threading.Lock()
        self._semaphores: dict[str, threading.Semaphore] = {}

    # ---------------- 对外三个入口 ----------------
    @property
    def available(self) -> bool:
        return self.cfg.llm_enabled

    def health_check(self) -> dict:
        """给系统状态页用：真实发一次最小请求，确认网关/Key 是否可用。"""
        if not self.cfg.llm_enabled:
            return {"ok": False, "mode": "mock", "detail": "离线规则兜底模式"}
        try:
            started = time.time()
            out = self.chat([{"role": "user", "content": "ping"}], tier="small",
                            customer_id="health", temperature=0)
            if not out:
                return {"ok": False, "mode": self.cfg.llm_provider,
                        "model": self._model("small"),
                        "detail": (self.last_error or "空响应")[:300]}
            return {"ok": True, "mode": self.cfg.llm_provider,
                    "latency_ms": round((time.time() - started) * 1000, 1),
                    "model": self._model("small"),
                    "detail": out[:60]}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "mode": self.cfg.llm_provider, "detail": str(exc)[:300]}

    def text(self, prompt: str, fallback: str = "", system: str | None = None,
             tier: str = "big", customer_id: str = "system",
             temperature: float | None = None) -> str:
        """自由文本生成。mock 模式直接返回 fallback。"""
        if not self.available:
            return fallback
        out = self._chat(
            messages=[m for m in ({"role": "system", "content": system} if system else None,
                                  {"role": "user", "content": prompt}) if m],
            tier=tier, customer_id=customer_id, temperature=temperature, json_mode=False,
        )
        return out if out else fallback

    def json(self, prompt: str, fallback=None, system: str | None = None,
             tier: str = "big", customer_id: str = "system",
             temperature: float | None = None):
        """结构化 JSON 生成。解析失败返回 fallback，保证下游永远拿到可用结构。"""
        if not self.available:
            return fallback
        out = self._chat(
            messages=[m for m in ({"role": "system", "content": system} if system else None,
                                  {"role": "user", "content": prompt}) if m],
            tier=tier, customer_id=customer_id, temperature=temperature, json_mode=True,
        )
        parsed = loads_lenient(out, default=None)
        return parsed if parsed is not None else fallback

    def chat(self, messages: list[dict], tier: str = "big", customer_id: str = "system",
             json_mode: bool = False, temperature: float | None = None) -> str:
        if not self.available:
            return ""
        return self._chat(messages, tier=tier, customer_id=customer_id,
                          temperature=temperature, json_mode=json_mode)

    # ---------------- 内部实现 ----------------
    def _model(self, tier: str) -> str:
        return self.cfg.llm_model_big if tier == "big" else self.cfg.llm_model_small

    def _sem(self, customer_id: str) -> threading.Semaphore:
        with self._sem_lock:
            if customer_id not in self._semaphores:
                self._semaphores[customer_id] = threading.Semaphore(
                    self.cfg.llm_max_concurrency_per_customer)
            return self._semaphores[customer_id]

    def _chat(self, messages: list[dict], tier: str, customer_id: str,
              temperature: float | None, json_mode: bool) -> str:
        model = self._model(tier)
        body_text = json.dumps(messages, ensure_ascii=False)
        key = make_key(model, temperature, json_mode, body_text)

        cached = self.cache.get(key)
        if cached is not None:
            self.stats.cache_hits += 1
            return cached

        payload = {
            "model": model,
            "messages": messages,
            "temperature": self.cfg.llm_temperature if temperature is None else temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        sem = self._sem(customer_id)
        with sem:
            started = time.time()
            self.stats.calls += 1
            self.stats.prompt_chars += len(body_text)
            out = ""
            usage: dict = {}
            last_error = ""
            for attempt in range(self.cfg.llm_max_retry + 1):
                try:
                    out, usage = self._post(payload)
                    break
                except Exception as exc:  # noqa: BLE001 - 统一兜底
                    last_error = str(exc)
                    if json_mode and "response_format" in last_error:
                        payload.pop("response_format", None)
                        continue
                    if attempt < self.cfg.llm_max_retry:
                        time.sleep(0.6 * (attempt + 1))
            self.stats.latency_ms += (time.time() - started) * 1000
            self.stats.prompt_tokens += int(usage.get("prompt_tokens") or 0)
            self.stats.completion_tokens += int(usage.get("completion_tokens") or 0)

        if not out:
            self.stats.failures += 1
            self.last_error = last_error or "空响应"
            if self.logger:
                self.logger.event("llm", "call_failed", level="ERROR",
                                  model=model, error=truncate(last_error, 200))
            return ""

        self.last_error = ""
        self.cache.set(key, out)
        if self.logger:
            self.logger.event("llm", "call_ok", model=model, tier=tier,
                              latency_ms=round((time.time() - started) * 1000, 1),
                              prompt_preview=truncate(body_text, 120))
        return out

    def _post(self, payload: dict) -> tuple[str, dict]:
        url = self.cfg.llm_base_url.rstrip("/") + "/chat/completions"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.cfg.llm_api_key:
            headers["Authorization"] = f"Bearer {self.cfg.llm_api_key}"
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.cfg.llm_timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")[:300]
            raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
        try:
            content = body["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"响应结构异常: {truncate(str(body), 200)}") from exc
        return content, dict(body.get("usage") or {})
