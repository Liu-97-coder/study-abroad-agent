"""Embedding 封装：默认离线 hashing 向量，可选 OpenAI 兼容接口（任务 1.1）。

hashing 向量的原理：中文取字二元组 + 英文取词，每个 token 用 md5 映射到
1024 维里的一个位置并带符号累加，最后 L2 归一化。它不是语义模型，但对
"院校名/GPA/专业名"这类关键词密集的检索足够用，且零依赖、零成本。
生产环境把 EMBED_BACKEND 换成 openai / bge 即可，接口不变。
"""
from __future__ import annotations

import hashlib
import json
import math
import urllib.request

from ..config import Settings, settings as default_settings
from ..utils.text_clean import tokenize


class HashedEmbedder:
    def __init__(self, dim: int = 1024):
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        tokens = tokenize(text)
        if not tokens:
            return vec
        weight = 1.0 / math.sqrt(len(tokens))
        for token in tokens:
            digest = hashlib.md5(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "little") % self.dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vec[idx] += sign * weight
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


class OpenAIEmbedder:
    def __init__(self, cfg: Settings):
        self.cfg = cfg

    def embed(self, text: str) -> list[float]:
        url = self.cfg.llm_base_url.rstrip("/") + "/embeddings"
        payload = {"model": self.cfg.embed_model, "input": text}
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.cfg.llm_api_key}"},
            method="POST")
        with urllib.request.urlopen(req, timeout=self.cfg.llm_timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return list(body["data"][0]["embedding"])

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


def build_embedder(cfg: Settings | None = None):
    cfg = cfg or default_settings
    if cfg.embed_backend == "openai" and cfg.llm_api_key:
        return OpenAIEmbedder(cfg)
    return HashedEmbedder(cfg.embed_dim)


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return float(sum(x * y for x, y in zip(a, b)))
