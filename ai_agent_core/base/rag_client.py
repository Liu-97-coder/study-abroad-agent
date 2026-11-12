"""统一向量知识库 RAG 框架（基座任务 1）。

四大 Collection 物理隔离：school / visa / writing / compliance。
检索三段式（任务 1.4）：标量前置过滤 → 稠密向量召回 → 重排序。

后端：
- local：JSON 文件 + 余弦相似度，零依赖，默认，适合开发/演示
- milvus：pymilvus + Milvus（Lite 或服务端），生产用，见 rag_milvus.py

每条数据都必须带 source_id，检索结果必须原样返回 source_info —— 这是
"防幻觉"的唯一抓手：没有来源的数字，一律不许出现在给客户的方案里。
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from ..config import COLLECTIONS, Settings, settings as default_settings
from ..schema.common_schema import RetrievedChunk
from ..utils.text_clean import jaccard, tokenize, truncate
from .embeddings import build_embedder, cosine

EMPTY_HINT = "【知识库未检索到匹配数据】不得编造院校门槛/截止日期/签证政策，请提示顾问人工确认或补充知识库。"


def split_text(text: str, size: int = 500, overlap: int = 100) -> list[str]:
    """按句子边界切分，避免把一句话切断（任务 1.3 的自适应分片）。"""
    text = (text or "").strip()
    if len(text) <= size:
        return [text] if text else []
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            window = text[start:end]
            for sep in ("。", "\n", "；", "！", "？", "."):
                cut = window.rfind(sep)
                if cut > size * 0.5:
                    end = start + cut + 1
                    break
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [c for c in chunks if c]


class RAGClient:
    def __init__(self, cfg: Settings | None = None, embedder=None, llm=None, logger=None):
        self.cfg = cfg or default_settings
        self.embedder = embedder or build_embedder(self.cfg)
        self.llm = llm
        self.logger = logger
        self._lock = threading.Lock()
        self._store: dict[str, list[dict]] = {name: [] for name in COLLECTIONS}
        self._dir = Path(self.cfg.runtime_dir) / "rag"
        self._dir.mkdir(parents=True, exist_ok=True)
        self.backend = self.cfg.rag_backend
        self._milvus = None
        if self.backend == "milvus":
            from .rag_milvus import MilvusBackend  # 懒加载，避免没装 pymilvus 就报错

            self._milvus = MilvusBackend(self.cfg, self.embedder)
        else:
            self._load_all()

    # ---------------- 持久化（local 后端） ----------------
    def _path(self, collection: str) -> Path:
        return self._dir / f"{collection}.json"

    def _load_all(self) -> None:
        for name in COLLECTIONS:
            path = self._path(name)
            if path.exists():
                try:
                    self._store[name] = json.loads(path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    self._store[name] = []

    def _save(self, collection: str) -> None:
        if self._milvus:
            return  # milvus 后端不写本地 JSON，否则会把 local 索引清空
        self._path(collection).write_text(
            json.dumps(self._store[collection], ensure_ascii=False), encoding="utf-8")

    # ---------------- 入库 ----------------
    def ingest(self, collection: str, docs: list[dict], replace: bool = False) -> int:
        """docs: [{text, metadata, source_id, source_name, update_time, valid_year}]"""
        if collection not in COLLECTIONS:
            raise ValueError(f"未知知识库 {collection}，可选：{list(COLLECTIONS)}")
        if self._milvus:
            return self._milvus.ingest(collection, docs, replace)

        with self._lock:
            if replace:
                self._store[collection] = []
            existing = {r["id"]: r for r in self._store[collection]}
            added = 0
            for doc in docs:
                text = doc.get("text", "")
                if not text.strip():
                    continue
                source_id = str(doc.get("source_id") or f"{collection}-{len(existing) + 1:04d}")
                vector = self.embedder.embed(text)
                record = {
                    "id": source_id,
                    "source_id": source_id,
                    "source_name": doc.get("source_name", ""),
                    "text": text,
                    "metadata": doc.get("metadata", {}),
                    "vector": vector,
                    "update_time": doc.get("update_time", ""),
                    "valid_year": doc.get("valid_year"),
                    "is_valid": bool(doc.get("is_valid", True)),
                }
                existing[source_id] = record
                added += 1
            self._store[collection] = list(existing.values())
            self._save(collection)

        if self.logger:
            self.logger.event("rag", "ingest", collection=collection, count=added)
        return added

    def ingest_file(self, collection: str, path: str | Path, source_name: str = "",
                    metadata: dict | None = None, size: int = 500, overlap: int = 100) -> int:
        """整份文档入库：自动分片，每片共享同一个 source_id（溯源粒度到"文档"）。"""
        path = Path(path)
        source_name = source_name or path.name
        text = path.read_text(encoding="utf-8")
        chunks = split_text(text, size=size, overlap=overlap)
        stem = path.stem
        self.delete_document(collection, f"{collection}:{stem}")
        docs = [
            {
                "text": chunk,
                "metadata": {**(metadata or {}), "chunk_index": idx, "source_name": source_name},
                "source_id": f"{collection}:{stem}"
                if len(chunks) == 1 else f"{collection}:{stem}#{idx}",
                "source_name": source_name,
                "update_time": self._today(),
                "valid_year": (metadata or {}).get("valid_year"),
            }
            for idx, chunk in enumerate(chunks)
        ]
        return self.ingest(collection, docs, replace=False)

    # ---------------- 检索 ----------------
    def search(self, collection: str, query: str, top_k: int | None = None,
               where: dict | None = None, rerank_top: int | None = None,
               use_llm_rerank: bool = False) -> list[RetrievedChunk]:
        top_k = top_k or self.cfg.rag_top_k
        rerank_top = rerank_top or self.cfg.rag_rerank_top
        if collection not in COLLECTIONS:
            return []
        if self._milvus:
            return self._milvus.search(collection, query, top_k, where, rerank_top)

        query_vec = self.embedder.embed(query)
        with self._lock:
            rows = list(self._store[collection])

        # 第一层：标量前置过滤（先把不匹配的剔除，再算向量，省算力）
        candidates = [r for r in rows if r.get("is_valid", True) and _match_meta(r.get("metadata", {}), where)]
        if not candidates:
            return []

        # 第二层：向量召回
        scored = [(cosine(query_vec, r["vector"]), r) for r in candidates]
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:top_k]

        # 第三层：重排序（关键词重叠加权；配了真实 LLM 可换成 LLM 打分）
        q_tokens = set(tokenize(query))
        ranked = []
        for vec_score, record in top:
            overlap = jaccard(q_tokens, set(tokenize(record["text"])))
            final = 0.75 * vec_score + 0.25 * overlap
            ranked.append((final, record))
        ranked.sort(key=lambda x: x[0], reverse=True)

        if use_llm_rerank and getattr(self.llm, "available", False):
            ranked = self._llm_rerank(query, ranked, rerank_top)

        results = [self._to_chunk(score, record) for score, record in ranked[:rerank_top]]
        if self.logger:
            self.logger.event("rag", "search", collection=collection,
                              query=truncate(query, 80), hits=len(results))
        return results

    def _llm_rerank(self, query: str, ranked: list[tuple[float, dict]], top_n: int):
        snippets = [f"[{i}] {truncate(r['text'], 160)}" for i, (_, r) in enumerate(ranked)]
        prompt = (
            "按与用户需求的相关性给下列知识片段排序，只输出最相关的编号 JSON 数组。\n"
            f"用户需求：{query}\n片段：\n" + "\n".join(snippets)
        )
        order = self.llm.json(prompt, fallback=None, tier="small")
        if not isinstance(order, list):
            return ranked
        picked = []
        for idx in order:
            if isinstance(idx, int) and 0 <= idx < len(ranked):
                picked.append(ranked[idx])
        return picked + [r for r in ranked if r not in picked][: max(0, top_n - len(picked))]

    @staticmethod
    def _to_chunk(score: float, record: dict) -> RetrievedChunk:
        return RetrievedChunk(
            content=record["text"],
            metadata=record.get("metadata", {}),
            score=round(float(score), 4),
            source_info={
                "source_id": record.get("source_id", ""),
                "source_name": record.get("source_name", ""),
                "update_time": record.get("update_time", ""),
                "valid_year": record.get("valid_year"),
            },
        )

    # ---------------- 运维 ----------------
    def update_document(self, collection: str, source_id: str, docs: list[dict]) -> int:
        """增量更新：删旧分片 → 写新版本（任务 1.5）。"""
        self.delete_document(collection, source_id)
        for doc in docs:
            doc.setdefault("source_id", source_id)
        return self.ingest(collection, docs)

    def delete_document(self, collection: str, source_id: str) -> int:
        if self._milvus:
            return 0
        with self._lock:
            before = len(self._store[collection])
            self._store[collection] = [
                r for r in self._store[collection]
                if r.get("source_id") != source_id and not r.get("source_id", "").startswith(f"{source_id}#")
            ]
            removed = before - len(self._store[collection])
            self._save(collection)
        return removed

    def invalidate(self, collection: str, source_id: str) -> int:
        """标为过期而不是物理删除：保留可追溯性，检索自动过滤。"""
        if self._milvus:
            return 0
        count = 0
        with self._lock:
            for record in self._store[collection]:
                if record.get("source_id", "").startswith(source_id):
                    record["is_valid"] = False
                    count += 1
            self._save(collection)
        return count

    def stats(self) -> dict:
        if self._milvus:
            return self._milvus.stats()
        return {name: len(rows) for name, rows in self._store.items()}

    @staticmethod
    def format_context(chunks: list[RetrievedChunk], max_chars: int = 4000) -> str:
        """把检索结果整理成 LLM 友好上下文，每段都带来源，方便模型引用。"""
        if not chunks:
            return EMPTY_HINT
        blocks, used = [], 0
        for i, chunk in enumerate(chunks, 1):
            sid = chunk.source_info.get("source_id", "unknown")
            name = chunk.source_info.get("source_name", "")
            block = f"[{i}]（来源：{name} | {sid}）\n{chunk.content}"
            if used + len(block) > max_chars:
                break
            blocks.append(block)
            used += len(block)
        return "\n\n".join(blocks)

    @staticmethod
    def _today() -> str:
        from datetime import date

        return date.today().isoformat()


def _match_meta(meta: dict, where: dict | None) -> bool:
    """标量过滤：支持等值、$in、$gte/$lte/$gt/$lt、$ne。"""
    if not where:
        return True
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
            for op, cmp in (("$gte", lambda a, b: a >= b), ("$lte", lambda a, b: a <= b),
                            ("$gt", lambda a, b: a > b), ("$lt", lambda a, b: a < b)):
                if op in cond:
                    if value is None:
                        return False
                    try:
                        if not cmp(value, cond[op]):
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
