"""带 TTL 的内存缓存。对应基座任务 1.7 / 3.6 的缓存与限流。"""
from __future__ import annotations

import hashlib
import threading
import time
from typing import Any, Callable


def make_key(*parts: Any) -> str:
    raw = "||".join(str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


class TTLCache:
    """线程安全的简易 TTL 缓存（生产可换 Redis，接口保持一致）。"""

    def __init__(self, ttl: int = 3600, max_size: int = 2048):
        self.ttl = ttl
        self.max_size = max_size
        self._data: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Any | None:
        with self._lock:
            item = self._data.get(key)
            if not item:
                self.misses += 1
                return None
            expire_at, value = item
            if expire_at < time.time():
                self._data.pop(key, None)
                self.misses += 1
                return None
            self.hits += 1
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            if len(self._data) >= self.max_size:
                oldest = min(self._data.items(), key=lambda kv: kv[1][0])
                self._data.pop(oldest[0], None)
            self._data[key] = (time.time() + self.ttl, value)

    def get_or_set(self, key: str, factory: Callable[[], Any]) -> Any:
        value = self.get(key)
        if value is not None:
            return value
        value = factory()
        self.set(key, value)
        return value

    def stats(self) -> dict:
        with self._lock:
            return {"size": len(self._data), "hits": self.hits, "misses": self.misses}


class TokenBucket:
    """单 key 限流（默认单 IP 每分钟 20 次）。"""

    def __init__(self, capacity: int = 20, per_seconds: int = 60):
        self.capacity = capacity
        self.per_seconds = per_seconds
        self._bucket: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str = "default") -> bool:
        now = time.time()
        with self._lock:
            stamps = [t for t in self._bucket.get(key, []) if now - t < self.per_seconds]
            if len(stamps) >= self.capacity:
                self._bucket[key] = stamps
                return False
            stamps.append(now)
            self._bucket[key] = stamps
            return True
