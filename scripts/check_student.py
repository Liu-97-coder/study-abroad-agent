"""学生端自检：链接生成 → 查看进度 → 上传材料 → 校验结果 → 进度更新。

用法：
    python scripts/check_student.py --base http://127.0.0.1:8000 --customer demo-001
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def call(base: str, path: str, payload: dict | None = None, token: str | None = None):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(base.rstrip("/") + path, data=data,
                                 method="POST" if data else "GET", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            return exc.code, {}


def upload(base: str, key: str, material: str, filename: str, content: bytes):
    boundary = "----check" + uuid.uuid4().hex
    parts = []
    for name, value in (("key", key), ("material_name", material)):
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
    parts.append(
        (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
         f"Content-Type: text/plain\r\n\r\n").encode() + content + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    req = urllib.request.Request(
        base.rstrip("/") + "/api/student/upload", data=body, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            return exc.code, {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--customer", default="demo-001")
    parser.add_argument("--admin", default="admin")
    parser.add_argument("--password", default="admin123")
    args = parser.parse_args()
    base = args.base

    results: list[tuple[str, bool, str]] = []

    def check(name, ok, detail=""):
        results.append((name, ok, detail))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}  {detail}")

    print("① 顾问生成学生端链接")
    status, body = call(base, "/api/auth/login", {"username": args.admin, "password": args.password})
    token = (body.get("data") or {}).get("token")
    check("顾问登录", bool(token))
    if not token:
        return 2

    status, body = call(base, f"/api/customer/{args.customer}/student-link", token=token)
    link = (body.get("data") or {})
    key = link.get("key", "")
    check("拿到 access_key", bool(key), f"url={link.get('url')}")
    if not key:
        return 2

    print("\n② 学生视角（免登录）")
    status, body = call(base, f"/api/student/view?key={key}")
    data = body.get("data") or {}
    check("打开学生端", status == 200 and data.get("customer_name") is not None,
          f"阶段={data.get('stage_label')} 待交={len(data.get('missing') or [])} 项")
    check("不泄露顾问内部信息",
          "risk_tags" not in json.dumps(data, ensure_ascii=False)
          and "workorders" not in json.dumps(data, ensure_ascii=False))
    materials = [m["name"] for m in data.get("materials") or []]
    print(f"     材料清单（{len(materials)}）：" + "、".join(materials[:6]) + " …")

    print("\n③ 上传材料并自动校验")
    target = "存款证明" if "存款证明" in materials else (materials[0] if materials else "存款证明")
    content = "中国银行 存款证明 存款金额 400000 元 存入日期 2026-06-01 存期 180 天".encode("utf-8")
    status, body = upload(base, key, target, "deposit.txt", content)
    payload = body.get("data") or {}
    check(f"上传「{target}」", status == 200 and body.get("code") == 0,
          f"pass={payload.get('pass')} type={payload.get('file_type')}")
    risks = payload.get("risks") or []
    for risk in risks[:3]:
        print(f"     · [{risk['level']}] {risk['desc'][:40]} → {risk['fix'][:30]}")

    print("\n④ 进度随之更新")
    status, body = call(base, f"/api/student/view?key={key}")
    data = body.get("data") or {}
    uploaded = [u["name"] for u in data.get("uploaded") or []]
    check("已上传列表包含该材料", target in uploaded, f"uploaded={uploaded}")

    print("\n④b 图片（拍照）上传走 OCR")
    sample = ROOT / "runtime" / "samples" / "sample_deposit.png"
    if sample.exists():
        status, body = upload(base, key, "存款证明", sample.name, sample.read_bytes())
        payload = body.get("data") or {}
        check("图片上传成功", status == 200 and body.get("code") == 0,
              f"type={payload.get('file_type')} 置信度={payload.get('confidence')}")
        check("图片里的金额被抽出来", payload.get("confidence", 0) > 0,
              f"pass={payload.get('pass')}")
    else:
        print("     （跳过：先跑 python scripts/ocr_demo.py 生成样例图）")

    print("\n⑤ 安全边界")
    status, _ = call(base, "/api/student/view?key=wrong-key-123")
    check("错误 key → 404", status == 404, f"status={status}")
    status, _ = call(base, f"/api/student/view?key={key}")
    check("学生端不需要登录", status == 200, f"status={status}")

    failed = [r for r in results if not r[1]]
    print(f"\n{'全部通过 ✅' if not failed else f'{len(failed)} 项未通过 ❌'}")
    print(f"\n学生端地址：{base}/student.html?k={key}")
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
