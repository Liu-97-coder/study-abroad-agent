"""通用文档 OCR & 结构化抽取（基座任务 2）。

真实场景：PaddleOCR 识别图片/PDF → 文本 → 规则引擎抽实体 → LLM 补漏 → 冲突校验。
本项目默认 stub 后端（直接吃文本 / txt / md / 可选的 PDF），保证离线可跑；
OCR_BACKEND=paddleocr 时走真实识别，接口完全一致。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ..config import Settings, settings as default_settings

DOC_TYPES = {
    "成绩单": ["成绩单", "transcript", "gpa", "学分", "课程", "平均分"],
    "存款证明": ["存款", "银行", "余额", "deposit", "定期", "存期"],
    "Offer": ["offer", "conditional", "unconditional", "录取", "university of"],
    "护照": ["passport", "护照", "签发", "有效期", "nationality"],
    "在读证明": ["在读", "学籍", "enrolment", "enrollment"],
    "毕业证": ["毕业证", "学位证", "graduation", "degree certificate"],
    "语言成绩": ["ielts", "toefl", "雅思", "托福"],
}

_MONEY_UNIT = {"万": 10000, "万元": 10000, "元": 1, "RMB": 1, "人民币": 1, "元整": 1}


@dataclass
class ExtractedDoc:
    file_type: str = "未知"
    raw_text: str = ""
    entities: dict = field(default_factory=dict)
    masked_text: str = ""
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    confidence: float = 0.0


def _num(text: str) -> float:
    return float(text.replace(",", "").replace("，", ""))


class OCRClient:
    def __init__(self, cfg: Settings | None = None, llm=None, logger=None):
        self.cfg = cfg or default_settings
        self.llm = llm
        self.logger = logger

    # ---------------- 文本获取 ----------------
    def read_text(self, path: str | Path | None) -> str:
        if not path:
            return ""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在：{path}")
        suffix = path.suffix.lower()
        if suffix in {".txt", ".md", ".csv", ".json"}:
            return path.read_text(encoding="utf-8", errors="ignore")
        if suffix == ".pdf":
            try:
                from pypdf import PdfReader  # type: ignore
            except ImportError as exc:
                raise RuntimeError("解析 PDF 需要 pypdf：pip install pypdf") from exc
            reader = PdfReader(str(path))
            return "\n".join((page.extract_text() or "") for page in reader.pages)
        if suffix in {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}:
            return self._ocr_image(path)
        raise RuntimeError(f"暂不支持的格式：{suffix}（支持 txt/md/csv/pdf/图片）")

    def _paddle_ocr(self, path: Path) -> str:
        if self.cfg.ocr_backend not in {"paddleocr"}:
            raise RuntimeError(
                "图片识别需要 OCR_BACKEND=paddleocr（或 rapidocr），当前是 "
                f"{self.cfg.ocr_backend}")
        try:
            from paddleocr import PaddleOCR  # type: ignore
        except ImportError as exc:
            raise RuntimeError("pip install paddleocr paddlepaddle") from exc
        engine = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
        result = engine.ocr(str(path), cls=True)
        lines = [item[1][0] for page in (result or []) for item in (page or [])]
        return "\n".join(lines)

    # ---------------- 图片识别（rapidocr，Windows 上最省事） ----------------
    _rapid_engine = None

    @classmethod
    def _get_rapid_engine(cls):
        """模型加载要 1-2 秒，进程内复用。"""
        if cls._rapid_engine is None:
            try:
                from rapidocr_onnxruntime import RapidOCR
            except ImportError as exc:
                raise RuntimeError(
                    "图片识别需要：pip install rapidocr-onnxruntime pillow"
                ) from exc
            cls._rapid_engine = RapidOCR()
        return cls._rapid_engine

    def _rapid_ocr(self, path: Path) -> str:
        engine = self._get_rapid_engine()
        image = self._preprocess(path)
        result, _ = engine(image)
        if not result:
            raise RuntimeError("未识别到文字（图片可能空白/过暗/分辨率太低）")
        # result: [[box, text, score], ...]
        lines = [row[1] for row in result if len(row) >= 2 and row[1]]
        return "\n".join(str(x) for x in lines)

    @staticmethod
    def _preprocess(path: Path):
        """统一转 RGB + 小图放大，明显提升手机拍照的识别率。"""
        try:
            from PIL import Image, ImageOps
        except ImportError as exc:
            raise RuntimeError("图片预处理需要 pillow：pip install pillow") from exc
        image = Image.open(path)
        image = ImageOps.exif_transpose(image)      # 手机照片的旋转信息
        image = image.convert("RGB")
        if image.width < 900:
            scale = 900 / image.width
            image = image.resize((int(image.width * scale), int(image.height * scale)))
        return image

    def _ocr_image(self, path: Path) -> str:
        backend = self.cfg.ocr_backend
        if backend == "paddleocr":
            return self._paddle_ocr(path)
        if backend == "stub":
            # stub 仍尝试用 rapidocr（装了就能用），没装则给明确提示
            try:
                return self._rapid_ocr(path)
            except RuntimeError as exc:
                raise RuntimeError(
                    f"{exc}；或把 .env 里 OCR_BACKEND 设为 rapidocr") from exc
        return self._rapid_ocr(path)

    # ---------------- 分类 ----------------
    @staticmethod
    def classify(text: str) -> str:
        low = (text or "").lower()
        scores = {name: sum(1 for kw in kws if kw in low) for name, kws in DOC_TYPES.items()}
        best = max(scores, key=lambda k: scores[k])
        return best if scores[best] > 0 else "未知"

    # ---------------- 实体抽取（规则层） ----------------
    @staticmethod
    def extract_entities(text: str) -> dict:
        text = text or ""
        entities: dict = {}
        warnings: list[str] = []

        m = re.search(r"(?:GPA|绩点)[^\d\n]{0,10}([0-9](?:\.[0-9]{1,2})?)(?:\s*[/／]\s*(5\.0|4\.0|100))?", text, re.I)
        if m:
            entities["gpa"] = float(m.group(1))
            if m.group(2):
                entities["gpa_scale"] = float(m.group(2))

        m = re.search(r"(?:均分|平均分|平均成绩|average score)[^\d\n]{0,10}([0-9]{2,3}(?:\.[0-9]{1,2})?)", text, re.I)
        if m:
            entities["average_score"] = float(m.group(1))

        m = re.search(r"(?:IELTS|雅思)[^\d\n]{0,10}([4-9](?:\.[05])?)", text, re.I)
        if m:
            entities["ielts"] = float(m.group(1))
        m = re.search(r"(?:TOEFL|托福)[^\d\n]{0,10}([0-9]{2,3})", text, re.I)
        if m:
            entities["toefl"] = int(m.group(1))
        m = re.search(r"(?:GRE)[^\d\n]{0,8}([0-9]{3})", text, re.I)
        if m:
            entities["gre"] = int(m.group(1))
        m = re.search(r"(?:GMAT)[^\d\n]{0,8}([0-9]{3})", text, re.I)
        if m:
            entities["gmat"] = int(m.group(1))

        m = re.search(r"(?:存款金额|存款余额|余额|存入金额|存款)[^\d\n]{0,10}"
                      r"([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*(万元|万|元|RMB|人民币)?", text, re.I)
        if m:
            amount = _num(m.group(1))
            unit = m.group(2) or "元"
            entities["fund_amount"] = amount * _MONEY_UNIT.get(unit, 1)
            entities["fund_currency"] = "CNY"

        m = re.search(r"(?:存入日期|开户日期|存入时间|起息日)[^\d\n]{0,8}"
                      r"(\d{4})[-年/.](\d{1,2})[-月/.](\d{1,2})", text)
        if m:
            entities["deposit_date"] = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

        m = re.search(r"(?:存期|存款期限|定期)[^\d\n]{0,6}([0-9]{1,3})\s*(天|日|个月|月)", text)
        if m:
            days = int(m.group(1)) * (30 if "月" in m.group(2) else 1)
            entities["deposit_days"] = days

        m = re.search(r"(?:押金|留位费|deposit)[^\d\n]{0,12}"
                      r"([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*(英镑|GBP|美元|USD|元|万)?", text, re.I)
        if m:
            entities["deposit_amount"] = _num(m.group(1))
            entities["deposit_currency"] = m.group(2) or ""

        m = re.search(r"(?:截止|deadline|due)[^\d\n]{0,12}(\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?)", text, re.I)
        if m:
            entities["deadline"] = m.group(1)

        m = re.search(r"\b([EGD][0-9]{8})\b", text)
        if m:
            entities["passport_no"] = m.group(1)
        m = re.search(r"\b([0-9]{17}[0-9Xx])\b", text)
        if m:
            entities["id_no"] = m.group(1)
        m = re.search(r"\b([0-9]{16,19})\b", text)
        if m:
            entities["bank_card"] = m.group(1)

        # 姓名：OCR 常把下一行连在一起（"姓名：李同学专业：计算机"），用后向断言截断
        m = re.search(r"(?:姓名|Name)[:：\s]{0,3}([\u4e00-\u9fa5]{2,4}?)"
                      r"(?=专业|性别|出生|民族|学号|$|\s|：|:|，|,)", text)
        if m:
            entities["name"] = m.group(1).strip()
        m = re.search(r"(?:专业|Major)[:：\s]{0,3}([\u4e00-\u9fa5A-Za-z]{2,20}?)(?=姓名|学号|$|\s|：|:)", text)
        if m:
            entities["major"] = m.group(1).strip()
        m = re.search(r"([\u4e00-\u9fa5]{2,12}(?:大学|学院))", text)
        if m:
            entities["school_name"] = m.group(1)

        m = re.search(r"(?:毕业时间|预计毕业|graduation)[^\d\n]{0,8}(\d{4})", text, re.I)
        if m:
            entities["graduation_year"] = int(m.group(1))

        if not entities:
            warnings.append("未抽取到任何结构化字段，可能是空白/加密/模糊文件")
        entities["_warnings"] = warnings
        return entities

    # ---------------- 脱敏 ----------------
    @staticmethod
    def mask(text: str) -> str:
        """脱敏。注意中文紧贴证件号时 `\\b` 不成立，所以用前后断言而不是单词边界。"""
        text = text or ""
        text = re.sub(r"(?<![A-Za-z0-9])([EGD][0-9]{4})[0-9]{4}(?![0-9])", r"\1****", text)
        text = re.sub(r"(?<![0-9])([0-9]{6})[0-9]{8}([0-9]{3}[0-9Xx])(?![0-9])",
                      r"\1********\2", text)
        text = re.sub(r"(?<![0-9])([0-9]{4})[0-9]{8,11}([0-9]{4})(?![0-9])",
                      r"\1********\2", text)
        return text

    # ---------------- 对外主入口 ----------------
    def parse(self, path: str | Path | None = None, text: str | None = None,
              file_type: str | None = None) -> ExtractedDoc:
        doc = ExtractedDoc()
        try:
            raw = text if text is not None else self.read_text(path)
        except Exception as exc:  # noqa: BLE001
            doc.errors.append(f"文件解析失败：{exc}")
            return doc

        if not (raw or "").strip():
            doc.errors.append("文件内容为空（空白文件/加密 PDF/损坏图片）")
            return doc

        doc.raw_text = raw
        doc.file_type = file_type or self.classify(raw)
        doc.entities = self.extract_entities(raw)
        doc.masked_text = self.mask(raw)
        doc.warnings.extend(doc.entities.get("_warnings", []))

        key_fields = {"成绩单": ["gpa", "average_score"], "存款证明": ["fund_amount", "deposit_days"],
                      "Offer": ["deadline"], "护照": ["passport_no"]}.get(doc.file_type, [])
        if key_fields:
            hit = sum(1 for k in key_fields if k in doc.entities)
            doc.confidence = round(hit / len(key_fields), 2)
            if hit < len(key_fields):
                doc.warnings.append(f"{doc.file_type}关键字段识别不全，需人工复核")

        if self.logger:
            self.logger.event("ocr", "parse", file_type=doc.file_type,
                              confidence=doc.confidence, errors=len(doc.errors))
        return doc
