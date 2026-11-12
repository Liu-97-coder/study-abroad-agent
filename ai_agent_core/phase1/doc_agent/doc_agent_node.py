"""文书 Agent 的 LangGraph 节点封装（文书 Agent 步骤 7）。"""
from __future__ import annotations

from datetime import datetime

from ...base.base_agent import BaseAgent
from ...schema.document_schema import DocResult
from ...schema.state_schema import CustomerState
from ...schema.student_schema import StudentBasicInfo
from .cv_generator import generate_cv
from .doc_quality_check import check_document
from .doc_version_mgr import DocVersionManager
from .experience_parse import build_experience_text, parse_experiences
from .ps_generator import generate_ps
from .ref_generator import generate_refs

QUALITY_PASS_LINE = 60.0


class DocumentAgent(BaseAgent):
    name = "document_agent"

    def _run(self, state: CustomerState) -> CustomerState:
        student = StudentBasicInfo(**{k: v for k, v in state.student_info.items()
                                      if k in StudentBasicInfo.model_fields})
        raw_exp = (state.student_info.get("experiences")
                   or state.student_info.get("raw_experiences") or "")
        experiences = parse_experiences(raw_exp, student_name=student.school_name or "")
        if not experiences:
            self.tag(state, "文书素材缺失", level="高", reason="未提供任何教育/实习/科研经历")
            self.task(state, "向学生收集实习/科研/项目素材", level="紧急", source=self.name)

        # 1) CV → 2) PS（带 RAG 课程素材）→ 3) 推荐信双风格双版本
        cv = generate_cv(student, experiences, self.ctx, state.customer_id)
        ps = generate_ps(student, experiences, self.ctx, state.customer_id)
        refs = generate_refs(student, experiences, self.ctx, state.customer_id)

        # 4) 质检（PS 为主，CV 附检）
        major_context = "\n".join(
            c.content for c in self.rag.search(
                "writing", f"{student.target_major or ''} 课程 培养目标", top_k=8, rerank_top=4))
        quality = check_document(ps["content"], student, experiences, major_context,
                                 self.ctx, state.customer_id)
        if quality["total"] < QUALITY_PASS_LINE:
            self.tag(state, "文书质检不达标", level="高",
                     reason=f"质检 {quality['total']} 分，低于 {QUALITY_PASS_LINE}")
            self.task(state, "文书组长复核并重写不合格段落", level="紧急", source=self.name)
        else:
            self.task(state, "顾问确认文书版本并发送学生", level="普通", source=self.name)

        # 5) 版本存档（AI 生成内容必须留痕可追溯）
        mgr = DocVersionManager(self.storage, self.logger)
        versions = mgr.save_bundle(state.customer_id, {
            "PS": ps["content"],
            "CV": cv["content"],
            "推荐信-学术": refs["academic"][0],
            "推荐信-企业": refs["corporate"][0],
            "原始素材": build_experience_text(experiences),
        })

        result = DocResult(
            cv_content=cv["content"],
            ps_content=ps["content"],
            ref1_content=refs["academic"][0],
            ref2_content=refs["corporate"][0],
            quality_score=quality["total"],
            quality_report="；".join(quality["comments"]),
            version_id=versions.get("PS", ""),
            create_time=datetime.now().isoformat(timespec="seconds"),
            major_family=cv["major_family"],
            sources=ps.get("sources", []),
        )

        state.out("document", {
            "result": result.model_dump(),
            "quality": quality,
            "versions": versions,
            "experience_count": len(experiences),
            "refs": refs,
        })
        if state.stage in {"material", "signed"}:
            state.stage = "document"
        return state
