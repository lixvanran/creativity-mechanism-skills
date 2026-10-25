#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ 生成 SHA256SUMS.txt（★ 可复现的清单生成器 ★）

============================================================
★ 为什么要有这个脚本（★ 2026-10-25 维护时发现 ★）
============================================================
★ 事件：★ 仓里的 SHA256SUMS.txt 是【从脏树】生成的 ⇒ ★ 它把 8 个
★   `__pycache__/*.pyc` 也列了进去（★ 而 .gitignore 本来就排除了它们 ★）
★   ⇒ ★ `sha256sum -c SHA256SUMS.txt` 报 **8 个文件读不到** ⇒ **43/51** ★
★   ⇒ ★ 而 README 把"sha256sum -c"列为完整性自检 ⇒ ★ **照着做就失败** ★
★ ⇒ ★ 根因：★ 清单不是【可复现地】从【仓的实际内容】生成的 ★
★ ⇒ ★ 落法：★ 清单 = ★ git 实际跟踪的文件 ★（★ 排除清单自身 ★）★ ⇒ ★ 一次生成、★ 永远对得上 ★
============================================================

★ 用法：★ `python3 make_manifest.py`（★ 写 SHA256SUMS.txt ★）
★ ★ 它【只写清单、不改任何其它文件】★ ⇒ ★ 与 `selfcheck.py`（只读、只判）职责分离 ★
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "SHA256SUMS.txt")
SELF = "SHA256SUMS.txt"


def tracked_files() -> list[str]:
    """★ 优先用 git ls-files（★ 清单 = 仓【实际跟踪】的内容 ★）★"""
    try:
        r = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                           text=True, timeout=60)
        if r.returncode == 0 and r.stdout.strip():
            # ★ 清单自身必须排除（★ git ls-files 会把它列出来 ★）
            #   ⇒ 否则 sha256sum -c 必然报"自己对自己不上"（★ 2026-10-25 实测 ★）
            return sorted(x for x in r.stdout.split("\n")
                          if x.strip() and x.strip() != SELF)
    except Exception:
        pass
    # 兜底：文件系统遍历（★ 排除 .git / __pycache__ / *.pyc / 清单自身 ★）
    out = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__")]
        for fn in filenames:
            if fn.endswith(".pyc"):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), ROOT).replace(os.sep, "/")
            if rel == SELF:
                continue
            out.append(rel)
    return sorted(out)


def sha256_file(p: str) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    files = tracked_files()
    lines = ["# creativity-mechanism-skills · 文件清单（★ sha256 ★）",
             "# 生成器：make_manifest.py（★ 清单 = git 跟踪的文件 ★，★ 排除本清单自身 ★）",
             "# 核对：python3 selfcheck.py（★ 或 sha256sum -c SHA256SUMS.txt ★）",
             ""]
    n_missing = 0
    for rel in files:
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            print("✘ 跟踪但文件不在：%s" % rel, file=sys.stderr)
            n_missing += 1
            continue
        lines.append("%s  %s" % (sha256_file(p), rel))
    if n_missing:
        print("✘ 有 %d 个文件缺失 ⇒ 清单未写出（★ 响亮失败 ★）" % n_missing, file=sys.stderr)
        return 1
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp, OUT)
    print("✅ 已写出 %s（%d 个文件）" % (os.path.basename(OUT), len(files)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
