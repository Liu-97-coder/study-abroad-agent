"""给某个客户的某个 Tab 拍单页截图（不重跑流程，适合展示真实产出）。

用法：
    python scripts/shot_tab.py --customer demo-001 --tab document --out docs/screenshots/08-document-llm.png
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--customer", default="demo-001")
    parser.add_argument("--tab", default="document")
    parser.add_argument("--out", default="docs/screenshots/tab.png")
    parser.add_argument("--user", default="admin")
    parser.add_argument("--password", default="admin123")
    parser.add_argument("--height", type=int, default=1020)
    args = parser.parse_args()

    from playwright.sync_api import sync_playwright

    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1500, "height": args.height})
        page.goto(args.base.rstrip("/") + "/", wait_until="networkidle")

        if page.evaluate("() => !!document.querySelector('#loginLayer:not([hidden])')"):
            page.fill("#loginUser", args.user)
            page.fill("#loginPass", args.password)
            page.click("#btnLogin")
            page.wait_for_function(
                "() => document.querySelector('#loginLayer').hidden === true", timeout=20_000)

        page.click('.nav-item[data-route="customers"]')
        selector = f'[data-open="{args.customer}"]'
        page.wait_for_selector(selector, timeout=15_000)
        page.click(selector)
        page.wait_for_timeout(1200)

        page.click(f'.tab[data-tab="{args.tab}"]')
        page.wait_for_timeout(1200)
        page.screenshot(path=str(out), full_page=True)
        browser.close()

    print(f"已保存：{out}（{out.stat().st_size // 1024} KB）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
