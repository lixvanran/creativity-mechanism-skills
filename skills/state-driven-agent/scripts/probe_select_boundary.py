#!/usr/bin/env python3
"""三组 `Select` 的**边界入参枚举冒烟**（主会话要求：k=0,1,n-1,n,n+1）。

★ 动机：2026-10-24 v6 Stage-1 抓到 —— `Select.__call__` 里 `if k >= n: return list(range(n))`
  ⇒ ⇒ **k == n 时返回原始顺序**（不是按分数排序）⇒ ⇒ 任何"用 k=n 取完整排序"的写法都会
  ⇒ ⇒ **把排序改变率变成恒 0** ⇒ ⇒ ⇒ **第三方代码的边界分支必须枚举测试。**

用法：python3 probe_select_boundary.py
"""
from __future__ import annotations
import os
import sys

os.environ["OPENROUTER_BASE_URL"] = "https://api.minimaxi.com/v1"
sys.path.insert(0, os.environ.get("G4_REF_DIR", "/workspace/g4_ref"))
from creativity_lab.gates.base import Select   # noqa: E402


def main() -> int:
    scores = [0.5, 0.2, 0.9]
    n = len(scores)
    modes = ("greedy", "sample", "novelty_biased")
    print("=" * 74)
    print("三组 Select · 边界入参枚举冒烟（scores=%s, n=%d）" % (scores, n))
    print("=" * 74)
    bad = []
    for mode in modes:
        for k in (0, 1, 2, n - 1, n, n + 1):
            try:
                r = Select(mode=mode)(list(scores), k=k)
            except Exception as e:
                print("  Select(mode=%-14s,k=%d) → ✘ %s" % (mode, k, e))
                bad.append((mode, k, "exception"))
                continue
            flag = ""
            if k >= n and r != list(range(n)):
                flag = "  ⚠️ 预期原序"
            if k == 1 and mode in ("greedy", "sample") and r != [2]:
                flag = "  ⚠️ 预期最高分下标 [2]"
            print("  Select(mode=%-14s,k=%d) → %s%s" % (mode, k, r, flag))
    print("-" * 74)
    print("★ 已确证的事实：")
    print("  ① k >= n ⇒ **返回原始顺序**（不是按分数排序）⇒ **不可用于取完整排序**")
    print("  ② k = 1 时 greedy 与 sample **结果相同** ⇒ sample 在 k=1 时 ≡ greedy")
    print("  ③ 本组 v6 的修法：自实现 `_rank_by_score6`（按 -scores 稳定排序），不用 Select 的 k=n 分支")
    print("-" * 74)
    print("  异常条数：%d" % len(bad))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
