"""全链路日志与 Trace 追踪（基座任务 3.5）。

一次客户流程共用同一个 trace_id，每个 Agent 的入参摘要/输出摘要/耗时
都落到 logs/trace-YYYYMMDD.jsonl，支持按 customer_id 回查。
"""
from __future__ import annotations

import json
import threading
import uuid
from collections import deque
from datetime import date, datetime
from pathlib import Path

from ..config import settings


class TraceLogger:
    def __init__(self, log_dir: Path | None = None):
        self.log_dir = Path(log_dir or settings.log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._buffer: deque[dict] = deque(maxlen=3000)
        self._file = self.log_dir / f"trace-{date.today():%Y%m%d}.jsonl"

    @staticmethod
    def new_trace_id() -> str:
        return "tr-" + uuid.uuid4().hex[:12]

    def event(
        self,
        agent: str,
        event: str,
        level: str = "INFO",
        trace_id: str = "",
        customer_id: str = "",
        **payload,
    ) -> dict:
        record = {
            "ts": datetime.now().isoformat(timespec="milliseconds"),
            "level": level,
            "agent": agent,
            "event": event,
            "trace_id": trace_id,
            "customer_id": customer_id,
            "payload": payload,
        }
        with self._lock:
            self._buffer.append(record)
            try:
                with self._file.open("a", encoding="utf-8") as fp:
                    fp.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            except OSError:
                pass
        return record

    def query(self, customer_id: str | None = None, trace_id: str | None = None,
              level: str | None = None, limit: int = 200) -> list[dict]:
        rows = list(self._buffer)
        if customer_id:
            rows = [r for r in rows if r["customer_id"] == customer_id]
        if trace_id:
            rows = [r for r in rows if r["trace_id"] == trace_id]
        if level:
            rows = [r for r in rows if r["level"] == level]
        return rows[-limit:]

    def stats(self) -> dict:
        rows = list(self._buffer)
        by_level: dict[str, int] = {}
        for r in rows:
            by_level[r["level"]] = by_level.get(r["level"], 0) + 1
        return {"records": len(rows), "by_level": by_level, "file": str(self._file)}
