"""图片 OCR 演示：生成两张样例证件图 → 识别 → 抽业务实体。

用法：
    python scripts/ocr_demo.py                 # 生成样例图并识别
    python scripts/ocr_demo.py --image 我的成绩单.png
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

from ai_agent_core.base.context import get_context  # noqa: E402
from ai_agent_core.config import RUNTIME_DIR  # noqa: E402

SAMPLES = RUNTIME_DIR / "samples"

FONTS = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
]


def _font(size: int):
    from PIL import ImageFont

    for path in FONTS:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def make_deposit() -> Path:
    from PIL import Image, ImageDraw

    SAMPLES.mkdir(parents=True, exist_ok=True)
    path = SAMPLES / "sample_deposit.png"
    image = Image.new("RGB", (1000, 620), "white")
    draw = ImageDraw.Draw(image)
    draw.text((60, 40), "中国银行", font=_font(40), fill="black")
    draw.text((60, 110), "存款证明", font=_font(48), fill="black")
    lines = [
        "户名：李同学",
        "存款金额：400000 元",
        "存入日期：2026-06-01",
        "存期：180 天",
        "账号：6217 **** **** 1234",
        "开具日期：2026-11-10",
    ]
    for idx, line in enumerate(lines):
        draw.text((60, 200 + idx * 62), line, font=_font(30), fill="black")
    draw.text((700, 540), "银行业务专用章", font=_font(24), fill=(180, 30, 30))
    image.save(path)
    return path


def make_transcript() -> Path:
    from PIL import Image, ImageDraw

    SAMPLES.mkdir(parents=True, exist_ok=True)
    path = SAMPLES / "sample_transcript.png"
    image = Image.new("RGB", (1000, 640), "white")
    draw = ImageDraw.Draw(image)
    draw.text((60, 40), "南京理工大学", font=_font(40), fill="black")
    draw.text((60, 110), "学生成绩单 TRANSCRIPT", font=_font(36), fill="black")
    lines = [
        "姓名：李同学    专业：计算机科学与技术",
        "GPA：3.6    均分：88",
        "课程：数据结构 92  操作系统 88  数据库 90",
        "预计毕业时间：2027-06",
    ]
    for idx, line in enumerate(lines):
        draw.text((60, 210 + idx * 66), line, font=_font(28), fill="black")
    draw.text((60, 560), "教务处盖章", font=_font(24), fill=(180, 30, 30))
    image.save(path)
    return path


def show(ctx, path: Path) -> None:
    doc = ctx.ocr.parse(path=path)
    print(f"\n=== {path.name} ===")
    if doc.errors:
        print("识别失败：", "；".join(doc.errors))
        return
    print(f"文件类型：{doc.file_type}  置信度：{doc.confidence}")
    print("--- 识别文本 ---")
    print(doc.raw_text.strip()[:500])
    print("--- 结构化实体 ---")
    for key, value in doc.entities.items():
        if key.startswith("_"):
            continue
        print(f"  {key}: {value}")
    if doc.warnings:
        print("提示：", "；".join(doc.warnings))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default="")
    args = parser.parse_args()

    ctx = get_context()
    print(f"OCR 后端：{ctx.settings.ocr_backend}（图片走 rapidocr）")

    if args.image:
        show(ctx, Path(args.image))
        return 0

    deposit = make_deposit()
    transcript = make_transcript()
    print(f"已生成样例图：{deposit.name}、{transcript.name}")
    print(f"目录：{SAMPLES}")
    show(ctx, deposit)
    show(ctx, transcript)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
