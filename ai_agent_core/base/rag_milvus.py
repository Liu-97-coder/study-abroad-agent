"""Milvus 后端适配（pymilvus 3.x + Milvus Lite / 独立服务）。

两种用法，靠环境变量区分：

    # A. 本地文件版（Milvus Lite，免 Docker，适合开发/演示）
    RAG_BACKEND=milvus
    MILVUS_LOCAL_PATH=./runtime/milvus_demo.db

    # B. 连独立 Milvus 服务（生产）
    RAG_BACKEND=milvus
    MILVUS_SERVER_URI=http://127.0.0.1:19530

注意：**不要**把变量叫 `MILVUS_URI` —— pymilvus 自己会读它当连接串，
填本地路径会让它 import 阶段就抛 `Illegal uri`。
"""
from __future__ import annotations

import json

from ..config import COLLECTIONS, Settings
from ..schema.common_schema import RetrievedChunk
from ..utils.text_clean import jaccard, tokenize


class MilvusBackend:
    def __init__(self, cfg: Settings, embedder):
        try:
            from pymilvus import MilvusClient
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "RAG_BACKEND=milvus 需要先安装：pip install pymilvus milvus-lite") from exc

        self.cfg = cfg
        self.embedder = embedder
        self.dim = cfg.embed_dim
        uri = cfg.milvus_server_uri or cfg.milvus_local_path
        self.client = MilvusClient(uri=uri)
        self.uri = uri
        self._loaded: set[str] = set()

        for name in COLLECTIONS:
            if not self.client.has_collection(name):
                self.client.create_collection(
                    collection_name=name,
                    dimension=self.dim,
                    primary_field_name="id",
                    id_type="string",
                    max_length=256,
                    vector_field_name="vector",
                    metric_type="COSINE",
                    auto_id=False,
                    enable_dynamic_field=True,
                )
            # 新建/重启后集合处于 released，必须 load 才能 search
            self._ensure_loaded(name)

    def _ensure_loaded(self, collection: str) -> None:
        if collection in self._loaded:
            return
        try:
            self.client.load_collection(collection)
        except Exception:  # noqa: BLE001 - 已加载或空集合都会抛，忽略
            pass
        self._loaded.add(collection)

    # ---------------- 写入 ----------------
    def ingest(self, collection: str, docs: list[dict], replace: bool = False) -> int:
        rows = []
        for doc in docs:
            text = (doc.get("text") or "").strip()
            if not text:
                continue
            source_id = str(doc.get("source_id") or f"{collection}-{len(rows)}")
            rows.append({
                "id": source_id,
                "vector": self.embedder.embed(text),
                "text": text,
                "source_id": source_id,
                "source_name": doc.get("source_name", ""),
                "metadata_json": json.dumps(doc.get("metadata", {}), ensure_ascii=False),
                "is_valid": True,
            })
        if not rows:
            return 0
        if replace:
            self.client.delete(collection_name=collection, filter="id != ''")
        self.client.upsert(collection_name=collection, data=rows)
        return len(rows)

    # ---------------- 检索 ----------------
    def search(self, collection: str, query: str, top_k: int, where: dict | None,
               rerank_top: int) -> list[RetrievedChunk]:
        self._ensure_loaded(collection)
        expr = "is_valid == true"
        hits = self.client.search(
            collection_name=collection,
            data=[self.embedder.embed(query)],
            limit=max(top_k, rerank_top),
            filter=expr,
            output_fields=["text", "source_id", "source_name", "metadata_json", "is_valid"],
        )[0]

        q_tokens = set(tokenize(query))
        ranked = []
        for hit in hits:
            entity = hit.get("entity", hit)
            if not _match_where(entity.get("metadata_json"), where):
                continue
            text = entity.get("text", "")
            score = 0.75 * float(hit.get("distance", 0)) + 0.25 * jaccard(q_tokens, set(tokenize(text)))
            ranked.append((score, entity))

        ranked.sort(key=lambda x: x[0], reverse=True)
        return [
            RetrievedChunk(
                content=entity.get("text", ""),
                metadata=_json(entity.get("metadata_json")),
                score=round(score, 4),
                source_info={"source_id": entity.get("source_id", ""),
                             "source_name": entity.get("source_name", "")},
            )
            for score, entity in ranked[:rerank_top]
        ]

    def stats(self) -> dict:
        out = {}
        for name in COLLECTIONS:
            try:
                out[name] = int(self.client.get_collection_stats(name).get("row_count", 0))
            except Exception:  # noqa: BLE001
                out[name] = 0
        return out


def _json(text) -> dict:
    if isinstance(text, dict):
        return text
    try:
        return json.loads(text or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}


def _match_where(metadata_json, where: dict | None) -> bool:
    """Milvus 侧只做向量检索，标量过滤在本地做一遍，逻辑与 local 后端完全一致。"""
    if not where:
        return True
    meta = _json(metadata_json)
    for key, cond in where.items():
        value = meta.get(key)
        if isinstance(cond, dict):
            if "$in" in cond:
                allowed = cond["$in"]
                if isinstance(value, list):
                    if not set(value) & set(allowed):
                        return False
                elif value not in allowed:
                    return False
            for op, fn in (("$gte", lambda a, b: a >= b), ("$lte", lambda a, b: a <= b),
                           ("$gt", lambda a, b: a > b), ("$lt", lambda a, b: a < b)):
                if op in cond:
                    if value is None:
                        return False
                    try:
                        if not fn(value, cond[op]):
                            return False
                    except TypeError:
                        return False
            if "$ne" in cond and value == cond["$ne"]:
                return False
        elif isinstance(cond, (list, tuple, set)):
            if isinstance(value, list):
                if not set(value) & set(cond):
                    return False
            elif value not in cond:
                return False
        elif value != cond:
            return False
    return True
