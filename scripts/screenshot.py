"""给 Web 控制台拍截图（用系统自带 Edge，无需下载浏览器）。

用法：
    python scripts/screenshot.py                       # 默认 http://127.0.0.1:8000
    python scripts/screenshot.py --base http://127.0.0.1:8002
产出：
    docs/screenshots/01-workbench.png  工作台（跑完选校）
    docs/screenshots/02-school.png     选校三档
    docs/screenshots/03-document.png   文书与质检
    docs/screenshots/04-dashboard.png  风控看板
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "screenshots"

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--width", type=int, default=1500)
    parser.add_argument("--height", type=int, default=1020)
    parser.add_argument("--user", default="admin")
    parser.add_argument("--password", default="admin123")
    parser.add_argument("--student-url", default="", help="学生端完整链接（含 ?k=），给了就顺便截图")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("需要 playwright：pip install playwright")
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    base = args.base.rstrip("/")

    with sync_playwright() as p:
        browser = None
        for channel in ("msedge", "chrome"):
            try:
                browser = p.chromium.launch(channel=channel, headless=True)
                print(f"使用浏览器：{channel}")
                break
            except Exception as exc:  # noqa: BLE001
                print(f"{channel} 不可用：{str(exc)[:80]}")
        if browser is None:
            try:
                browser = p.chromium.launch(headless=True)
                print("使用内置 chromium")
            except Exception as exc:  # noqa: BLE001
                print("启动浏览器失败：", exc)
                return 1

        page = browser.new_page(viewport={"width": args.width, "height": args.height},
                                device_scale_factor=1)
        page.goto(base + "/", wait_until="networkidle")
        page.wait_for_timeout(600)

        # 登录页（鉴权默认开启）
        need_login = page.evaluate("() => !!document.querySelector('#loginLayer:not([hidden])')")
        if need_login:
            page.screenshot(path=str(OUT / "00-login.png"))
            print("✓ 00-login.png")
            page.fill("#loginUser", args.user)
            page.fill("#loginPass", args.password)
            page.click("#btnLogin")
            page.wait_for_function("() => document.querySelector('#loginLayer').hidden === true",
                                   timeout=20_000)
            page.wait_for_timeout(800)

        page.screenshot(path=str(OUT / "01-workbench.png"))
        print("✓ 01-workbench.png")

        # 跑一次全流程，让各页有数据
        page.click("#btnRunAll")
        page.wait_for_selector("#stagePill.done, #stagePill.run", timeout=90_000)
        page.wait_for_timeout(1200)

        page.screenshot(path=str(OUT / "01-workbench.png"))
        print("✓ 01-workbench.png（含执行结果）")

        page.click('.tab[data-tab="school"]')
        page.wait_for_timeout(500)
        page.screenshot(path=str(OUT / "02-school.png"))
        print("✓ 02-school.png")

        page.click('.tab[data-tab="document"]')
        page.wait_for_timeout(500)
        page.screenshot(path=str(OUT / "03-document.png"))
        print("✓ 03-document.png")

        page.click('.nav-item[data-route="dashboard"]')
        page.wait_for_timeout(1200)
        page.screenshot(path=str(OUT / "04-dashboard.png"))
        print("✓ 04-dashboard.png")

        if args.student_url:
            mobile = browser.new_page(viewport={"width": 420, "height": 900},
                                      device_scale_factor=2)
            mobile.goto(args.student_url, wait_until="networkidle")
            mobile.wait_for_timeout(900)
            mobile.screenshot(path=str(OUT / "05-student.png"), full_page=True)
            print("✓ 05-student.png")

        # 面试 Tab：出题 + 答一题，展示评分
        try:
            page.click('.nav-item[data-route="workbench"]')
            page.wait_for_timeout(400)
            page.click('.tab[data-tab="interview"]')
            page.wait_for_timeout(400)
            page.click("#btnInterviewStart")
            page.wait_for_selector(".iv-item", timeout=30_000)
            page.wait_for_timeout(600)
            answer = ("当时我在银行实习，负责风控规则测试。我的任务是把上线前的漏测补上。"
                      "我先梳理 3 个核心场景，写了 120 条测试用例，用 Python 做批量回归，"
                      "最后发现 8 个规则漏洞，上线后零事故。")
            # 填第 2 题（学术题），答案与题目更匹配
            target = page.locator(".iv-item").nth(1)
            target.locator(".iv-answer").fill(answer)
            target.locator("[data-iv-answer]").click()
            page.wait_for_timeout(1600)
            page.screenshot(path=str(OUT / "07-interview.png"), full_page=True)
            print("✓ 07-interview.png")
        except Exception as exc:  # noqa: BLE001
            print(f"跳过面试截图：{str(exc)[:80]}")

        browser.close()
    print(f"\n输出目录：{OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
