"""学生端接口（公开，凭 access_key 访问）。

设计原则：学生只看"我该交什么、交到哪了、下一步干什么"，看不到内部风险评估、
顾问话术、渠道成本等敏感信息 —— 这是数据隔离的一部分，不是界面问题。
"""
from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..config import RUNTIME_DIR, STAGE_LABELS, STAGES
from ..phase2.material_agent.material_list_builder import build_custom_material_list
from ..phase2.material_agent.material_notice_generator import generate_notice
from ..phase2.material_agent.material_rule_checker import check_material
from ..phase2.material_agent.material_task_generator import missing_diff
from ..schema.common_schema import ApiResponse
from ..schema.state_schema import CustomerState
from ..schema.student_schema import StudentBasicInfo
from .deps import get_ctx

router = APIRouter(prefix="/api/student", tags=["学生端"])

UPLOAD_DIR = RUNTIME_DIR / "uploads"
STEP_KEYS = [("school", "选校定位"), ("material", "材料准备"), ("document", "文书制作"),
             ("application", "网申递交"), ("offer", "Offer/换无条件"), ("visa", "签证办理")]


def ensure_access_key(state: CustomerState) -> str:
    key = str(state.student_info.get("access_key") or "")
    if not key:
        key = secrets.token_urlsafe(6)
        state.student_info["access_key"] = key
        get_ctx().storage.save_customer(state)
    return key


def _find_by_key(key: str) -> CustomerState | None:
    if not key:
        return None
    for data in get_ctx().storage.list_customer_data(limit=2000):
        info = data.get("student_info") or {}
        if info.get("access_key") == key:
            return CustomerState(**data)
    return None


def _progress(state: CustomerState) -> list[dict]:
    outputs = state.agent_outputs or {}
    steps = []
    for key, label in STEP_KEYS:
        done = bool(outputs.get(key))
        steps.append({"key": key, "label": label, "done": done})
    return steps


def _student_brief(state: CustomerState) -> dict:
    student = StudentBasicInfo(**{k: v for k, v in state.student_info.items()
                                  if k in StudentBasicInfo.model_fields})
    items, _ = build_custom_material_list(student, get_ctx(),
                                          submit_deadline=str(state.student_info.get("submit_deadline", "")))
    uploaded = state.student_info.get("uploaded_files") or []
    passed = [u.get("name", "") for u in uploaded if u.get("pass_flag", True)]
    missing = missing_diff(items, passed)
    notice = generate_notice([m.material_name for m in missing], 0)
    return {
        "customer_name": state.customer_name,
        "stage": state.stage,
        "stage_label": STAGE_LABELS.get(state.stage, state.stage),
        "stage_index": STAGES.index(state.stage) if state.stage in STAGES else 0,
        "progress": _progress(state),
        "materials": [
            {"name": i.material_name, "required": i.is_required,
             "deadline": i.submit_deadline, "standard": i.check_standard}
            for i in items
        ],
        "missing": [m.material_name for m in missing],
        "uploaded": [
            {"name": u.get("name", ""), "pass_flag": u.get("pass_flag", True),
             "uploaded_at": u.get("uploaded_at", "")}
            for u in uploaded
        ],
        "notice": notice["student_text"] if missing else "材料已齐全，等待顾问下一步安排。",
        "target": {
            "country": "、".join(student.target_country),
            "major": student.target_major or "",
            "degree": student.target_degree or "",
        },
    }


@router.get("/view", response_model=ApiResponse)
def view(key: str):
    state = _find_by_key(key)
    if state is None:
        raise HTTPException(status_code=404, detail="链接无效或已失效")
    return ApiResponse.ok(_student_brief(state))


@router.get("/task", response_model=ApiResponse)
def task(key: str):
    """学生只看"待办"，不看顾问内部备注。"""
    state = _find_by_key(key)
    if state is None:
        raise HTTPException(status_code=404, detail="链接无效或已失效")
    return ApiResponse.ok({
        "current": [t["title"] for t in state.task_list
                    if t.get("status") == "open" and t.get("source") == "material_agent"][:10],
        "notice": _student_brief(state)["notice"],
    })


@router.post("/upload", response_model=ApiResponse)
async def upload(key: str = Form(...), material_name: str = Form(...),
                 file: UploadFile = File(...)):
    ctx = get_ctx()
    state = _find_by_key(key)
    if state is None:
        raise HTTPException(status_code=404, detail="链接无效或已失效")

    raw = await file.read()
    if not raw:
        return ApiResponse.fail("文件为空", code=400)
    if len(raw) > 10 * 1024 * 1024:
        return ApiResponse.fail("文件超过 10MB，请压缩后再传", code=400)

    suffix = Path(file.filename or "upload.bin").suffix.lower() or ".bin"
    target_dir = UPLOAD_DIR / state.customer_id
    target_dir.mkdir(parents=True, exist_ok=True)
    saved = target_dir / f"{secrets.token_hex(4)}{suffix}"
    saved.write_bytes(raw)

    # 解析：文本类直接读，PDF 走 pypdf，图片需要 paddleocr
    text = ""
    doc = None
    try:
        if suffix in {".txt", ".md", ".csv"}:
            text = raw.decode("utf-8", errors="ignore")
            doc = ctx.ocr.parse(text=text, file_type=None)
        else:
            doc = ctx.ocr.parse(path=saved)
    except Exception as exc:  # noqa: BLE001
        image_hint = "图片/扫描件请在 .env 里设置 OCR_BACKEND=paddleocr 并安装 paddleocr"
        return ApiResponse.fail(f"文件解析失败：{exc}。{image_hint}", code=400)

    student = StudentBasicInfo(**{k: v for k, v in state.student_info.items()
                                  if k in StudentBasicInfo.model_fields})
    country = (student.target_country or ["英国"])[0]
    result = check_material(material_name, doc, student, country)

    entry = {
        "name": material_name,
        "file": saved.name,
        "pass_flag": result.pass_flag,
        "uploaded_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "risk_count": len(result.risk_list),
        "extracted": {k: v for k, v in (doc.entities or {}).items() if not k.startswith("_")},
    }
    uploaded = list(state.student_info.get("uploaded_files") or [])
    uploaded = [u for u in uploaded if u.get("name") != material_name] + [entry]
    state.student_info["uploaded_files"] = uploaded
    ctx.storage.save_customer(state)

    ctx.logger.event("student", "upload", customer_id=state.customer_id,
                     material=material_name, pass_flag=result.pass_flag)

    return ApiResponse.ok({
        "material": material_name,
        "pass": result.pass_flag,
        "file_type": doc.file_type,
        "confidence": doc.confidence,
        "risks": [
            {"level": r.risk_level, "desc": r.risk_desc, "fix": r.fix_suggest}
            for r in result.risk_list
        ],
        "message": "校验通过，已收到" if result.pass_flag else "已收到，但有几处需要修正",
    })
