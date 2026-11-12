"""把当前目录发布到 GitHub（走 Git Data API，一次提交，不依赖本机 git 凭据）。

用法：
    set GITHUB_TOKEN=github_pat_xxx
    python scripts/publish_github.py --repo study-abroad-agent --private
    python scripts/publish_github.py --dry-run          # 只检查文件与密钥，不上传

为什么不用 git push：不需要配凭据助手/SSH key，token 只在内存里用，不落盘。
安全：自动跳过 .gitignore 里的内容，并在上传前扫一遍真实密钥形态，命中就中止。
"""
from __future__ import annotations

import argparse
import base64
import fnmatch
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

SKIP_DIRS = {".git", ".venv", "runtime", "logs", "__pycache__", ".pytest_cache",
             ".ruff_cache", ".idea"}
SKIP_FILES = {".env", ".env.bak"}
SKIP_PATTERNS = ["*.pyc", "*.pyo", "*.log", ".env.*", "*.bak", "Thumbs.db", ".DS_Store",
                 "data/output/*"]
SECRET_RE = re.compile(r"\bsk-[A-Za-z0-9]{24,}\b")
TEXT_SUFFIXES = {".py", ".md", ".json", ".yml", ".yaml", ".txt", ".csv", ".js", ".css",
                 ".html", ".bat", ".ps1", ".vbs", ".toml", ".ini", ".example"}


# ---------------- GitHub API ----------------
def api(method: str, path: str, token: str, payload: dict | None = None):
    url = "https://api.github.com" + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "study-abroad-agent-publisher",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode()
            return resp.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")[:400]
        return exc.code, {"error": detail}


# ---------------- 文件收集与安全检查 ----------------
def collect_files() -> list[Path]:
    out: list[Path] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        rel_path = path.relative_to(ROOT)
        rel = rel_path.as_posix()
        if any(part in SKIP_DIRS for part in rel_path.parts[:-1]):
            continue
        if rel in SKIP_FILES or any(fnmatch.fnmatch(rel, p) for p in SKIP_PATTERNS):
            # .gitignore 里的 !.env.example 反向规则要在这里显式实现
            if rel != ".env.example":
                continue
        out.append(path)
    return out


def _is_placeholder(token: str) -> bool:
    body = token[3:]
    return set(body.lower()) <= {"x", "0"}


def scan_secrets(files: list[Path]) -> list[str]:
    hits = []
    for path in files:
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name != ".env.example":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for match in SECRET_RE.finditer(text):
            if _is_placeholder(match.group(0)):
                continue
            hits.append(f"{path.relative_to(ROOT).as_posix()}: {match.group(0)[:10]}…")
            break
    return hits


# ---------------- 主流程 ----------------
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="study-abroad-agent")
    parser.add_argument("--private", action="store_true", default=True)
    parser.add_argument("--public", dest="private", action="store_false")
    parser.add_argument("--description",
                        default="留学全流程智能顾问 Agent 系统：RAG + 多 Agent 编排 + 风控护栏 + Web 控制台")
    parser.add_argument("--message", default="feat: 留学 Agent 系统完整实现")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    files = collect_files()
    total = sum(f.stat().st_size for f in files)
    print(f"① 收集文件：{len(files)} 个，{total / 1024 / 1024:.2f} MB")

    hits = scan_secrets(files)
    if hits:
        print("\n[中止] 发现疑似真实密钥：")
        for h in hits[:10]:
            print("   " + h)
        return 2
    print("   密钥扫描：通过")

    if args.dry_run:
        for f in files[:15]:
            print("   " + f.relative_to(ROOT).as_posix())
        print(f"   … 共 {len(files)} 个（dry-run，不上传）")
        return 0

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        print("\n缺少 GITHUB_TOKEN。先执行：set GITHUB_TOKEN=github_pat_xxx")
        return 2

    status, me = api("GET", "/user", token)
    if status != 200:
        print(f"Token 无效（HTTP {status}）：{me}")
        return 2
    owner = me["login"]
    print(f"② 身份：{owner}")

    status, repo = api("POST", "/user/repos", token, {
        "name": args.repo, "private": args.private,
        "description": args.description, "auto_init": False,
    })
    if status == 201:
        print(f"③ 已创建仓库：{repo.get('html_url')}")
    elif status == 422:
        print(f"③ 仓库已存在，继续推送：https://github.com/{owner}/{args.repo}")
    else:
        print(f"③ 建仓库失败（HTTP {status}）：{repo}")
        return 2

    # 空仓库不能直接建 blob（GitHub 返回 409），先用 Contents API 造一个初始提交
    status, ref = api("GET", f"/repos/{owner}/{args.repo}/git/ref/heads/main", token)
    if status != 200:
        status, init = api("PUT", f"/repos/{owner}/{args.repo}/contents/.gitkeep", token,
                           {"message": "chore: init repository", "content": ""})
        if status not in (200, 201):
            print(f"   初始化仓库失败：{status} {init}")
            return 2
        print("   已创建初始提交（空仓库需要）")

    print("④ 上传文件 …")
    tree = []
    for idx, path in enumerate(files, 1):
        content = base64.b64encode(path.read_bytes()).decode()
        status, blob = api("POST", f"/repos/{owner}/{args.repo}/git/blobs", token,
                           {"content": content, "encoding": "base64"})
        if status != 201:
            print(f"   失败：{path.relative_to(ROOT).as_posix()} → {status} {blob}")
            return 2
        tree.append({"path": path.relative_to(ROOT).as_posix(), "mode": "100644",
                     "type": "blob", "sha": blob["sha"]})
        if idx % 40 == 0:
            print(f"   {idx}/{len(files)}")

    print("⑤ 建 tree / commit / ref …")
    status, tree_resp = api("POST", f"/repos/{owner}/{args.repo}/git/trees", token,
                            {"tree": tree})
    if status != 201:
        print(f"   建 tree 失败：{status} {tree_resp}")
        return 2

    status, parent = api("GET", f"/repos/{owner}/{args.repo}/git/ref/heads/main", token)
    parents = [parent["object"]["sha"]] if status == 200 else []

    status, commit = api("POST", f"/repos/{owner}/{args.repo}/git/commits", token, {
        "message": args.message, "tree": tree_resp["sha"], "parents": parents,
    })
    if status != 201:
        print(f"   建 commit 失败：{status} {commit}")
        return 2

    if parents:
        status, _ = api("PATCH", f"/repos/{owner}/{args.repo}/git/refs/heads/main", token,
                        {"sha": commit["sha"], "force": False})
    else:
        status, _ = api("POST", f"/repos/{owner}/{args.repo}/git/refs", token,
                        {"ref": "refs/heads/main", "sha": commit["sha"]})
    if status not in (200, 201):
        print(f"   更新分支失败：{status}")
        return 2

    print(f"\n完成 ✅  https://github.com/{owner}/{args.repo}")
    print(f"  提交 {commit['sha'][:10]} · 文件 {len(files)} 个 · "
          f"{'私有' if args.private else '公开'}仓库")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
