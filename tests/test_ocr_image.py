"""图片 OCR 测试：需要 rapidocr + pillow，未安装时自动跳过。"""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("rapidocr_onnxruntime")
Image = pytest.importorskip("PIL.Image")
ImageDraw = pytest.importorskip("PIL.ImageDraw")
ImageFont = pytest.importorskip("PIL.ImageFont")

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
]


def _font(size: int):
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    pytest.skip("系统缺少中文字体，跳过图片 OCR 测试")
    return None


def _make_deposit_image(path: Path) -> Path:
    image = Image.new("RGB", (900, 520), "white")
    draw = ImageDraw.Draw(image)
    draw.text((50, 40), "中国银行", font=_font(36), fill="black")
    draw.text((50, 100), "存款证明", font=_font(44), fill="black")
    lines = ["存款金额：400000 元", "存入日期：2026-06-01", "存期：180 天"]
    for idx, line in enumerate(lines):
        draw.text((50, 200 + idx * 70), line, font=_font(30), fill="black")
    image.save(path)
    return path


def test_image_ocr_extracts_fund_entities(ctx, tmp_path):
    path = _make_deposit_image(tmp_path / "deposit.png")
    doc = ctx.ocr.parse(path=path)
    assert not doc.errors, doc.errors
    assert doc.file_type == "存款证明"
    assert doc.entities.get("fund_amount") == 400000
    assert doc.entities.get("deposit_days") == 180
    assert doc.confidence > 0


def test_image_ocr_masks_sensitive_data(ctx, tmp_path):
    image = Image.new("RGB", (900, 320), "white")
    draw = ImageDraw.Draw(image)
    draw.text((50, 60), "护照号 E12345678", font=_font(34), fill="black")
    path = tmp_path / "passport.png"
    image.save(path)

    doc = ctx.ocr.parse(path=path)
    assert "E12345678" not in doc.masked_text
    assert "*" in doc.masked_text


def test_unknown_suffix_reports_error(ctx, tmp_path):
    path = tmp_path / "x.docx"
    path.write_bytes(b"not supported")
    doc = ctx.ocr.parse(path=path)
    assert doc.errors and "不支持" in doc.errors[0]
