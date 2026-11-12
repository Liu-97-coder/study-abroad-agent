"""文书版本管理（文书 Agent 步骤 6）。

每次生成 = 一个 version_id，原始素材 / AI 初稿 / 人工修改 / 定稿全部留档。
作用有两个：界定"改几版"的合同边界；纠纷时能证明哪句话是 AI 写的、哪句是顾问改的。
"""
from __future__ import annotations

from datetime import datetime

STATUS_FLOW = ["待修改", "已审核", "最终版"]


class DocVersionManager:
    def __init__(self, storage, logger=None):
        self.storage = storage
        self.logger = logger

    def save(self, customer_id: str, doc_type: str, content: str,
             status: str = "待修改") -> str:
        version_id = self.storage.save_version(customer_id, doc_type, content, status)
        if self.logger:
            self.logger.event("doc_version", "save", customer_id=customer_id,
                              doc_type=doc_type, version_id=version_id, status=status,
                              chars=len(content))
        return version_id

    def save_bundle(self, customer_id: str, docs: dict[str, str]) -> dict[str, str]:
        return {doc_type: self.save(customer_id, doc_type, content)
                for doc_type, content in docs.items() if content}

    def list(self, customer_id: str, doc_type: str | None = None) -> list[dict]:
        return self.storage.list_versions(customer_id, doc_type)

    def approve(self, customer_id: str, version_id: str, status: str = "已审核") -> bool:
        if status not in STATUS_FLOW:
            raise ValueError(f"非法状态：{status}，可选 {STATUS_FLOW}")
        return self.storage.update_version_status(customer_id, version_id, status)

    @staticmethod
    def next_status(current: str) -> str:
        idx = STATUS_FLOW.index(current) if current in STATUS_FLOW else 0
        return STATUS_FLOW[min(idx + 1, len(STATUS_FLOW) - 1)]

    @staticmethod
    def audit_line(version_id: str, operator: str = "AI") -> str:
        return f"{datetime.now():%Y-%m-%d %H:%M} · {version_id} · 生成方：{operator}"
