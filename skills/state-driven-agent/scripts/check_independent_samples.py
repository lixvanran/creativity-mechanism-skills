#!/usr/bin/env python3
"""★ **独立采样判据（★ 2026-10-25 主会话追问后写死）**

★ **★ 问题**：★ Stage-1 的 `T10-1` 出现两条（★ 两个进程并发写）⇒ ⇒
★ ★ **那两条是【两次独立采样】还是【同一采样的重跑副本】？**
★ ★ ⇒ ★ **这直接动到独立样本数（n=9 还是 n=8）⇒ ⇒ ⇒ 动到 σ_new 的自由度、
★ ⇒ ⇒ 排序改变率 3/9 的分母、★ 以及三个 Gate 的 9/9 可用数。**

★ **★ 结论（★ 已用数据核实）**：★ **两次独立采样。★**

★ **★ 判据（★ 写死，★ 下次遇到同样的事必须用同一条）**：
★ **★ 一个单元的两次记录【相同】⇒ ★ 是重跑副本（★ 不得计入独立样本）
★ ★ 一个单元的两次记录【在下列【实质字段】上不同】⇒ ★ 是独立采样（★ 可计入独立样本）**

★ **★ 实质字段清单（★ 选它们的理由：★ 它们【只有在真的重新跑了那条链路时】才会变）**：

| ★ 字段 | ★ 为什么算实质 |
|---|---|
| ★ `A.text_len` | ★ **A 臂是独立的一次模型生成** ⇒ ★ 长度不同 ⇒ 正文不同 ⇒ **不可能是副本** |
| ★ `state_meta.decisions[].note` | ★ 状态链的**决策措辞** ⇒ ★ 模型重新推理过 ⇒ **不可能是副本** |
| ★ `state_meta.decisions[].depth` | ★ 决策**结构**不同 ⇒ 更强的证据（★ 结构变 ⇒ 不是措辞变） |
| ★ `F_family.picked_idx` / `per_gate` | ★ 选择器的**实际选择**不同 |
| ★ `D_state_quota.scores` / `B_state_nocost.scores` | ★ **候选声明不同** ⇒ ⇒ 评分不同 |
| ★ `ful_B` / `ful_D` / `ful_F` | ★ 兑现率不同 |
| ★ `rank_change_quota.changed` / `sel_change_*` | ★ **排序结论本身不同**（★ 最强证据） |

★ **★ 非实质字段（★ 即使相同也不影响独立性判断）**：
★ `tag` / `rep` / `batch_id` / `topic_id` / `model` / `question` / `seed` / `arm` /
★ `error` / `n_cand_ok` / `n_cand_scored` / `cand_errors` / `embed_error` / `_embed_rec` /
★ `target_base` / `target_quota` / `target_changed` / `quota_meta` / `calls` / `elapsed`

★ **★ 为什么 `target_base` / `target_quota` 不算实质**：★ 它们由**决策的 depth 分布**推导
★ ⇒ ⇒ ★ 两次采样可能给出【同样的深度分布】⇒ ⇒ **相同不代表副本**（★ ★ 这正是本例的情况：
★ ★ 两条的 `depth` 都是"深入/深入/点到为止"，★ 只有 `note` 措辞不同）。

★ **★ 为什么 `calls` / `elapsed` 不算**：★ 它们只说明"跑过"，★ 不说明"跑出了不同结果"。

★ **★ 机械执行**：★ `python3 -B group4_state_driven/check_independent_samples.py`
★ ⇒ ★ 打印每组重复单元的逐字段差异清单 ⇒ ★ 并给出【记录数 vs 独立样本数】两个数。
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(_HERE)
DATA = os.path.join(REPO, "group4_state_driven", "data")
# ★ 重标记【前】的原始文件（★ 保留在仓内 ⇒ ★ 可复核）
PRE = os.path.join(DATA, "arch6_stage1.pre_dedup.jsonl")

# ★ 实质字段（★ 变了 ⇒ 独立采样）
SUBSTANTIVE = [
    "A.text_len",
    "state_meta.decisions",
    "F_family.picked_idx",
    "F_family.per_gate",
    "D_state_quota.scores",
    "D_state_quota.picked_idx",
    "B_state_nocost.scores",
    "B_state_nocost.picked_idx",
    "ful_B",
    "ful_D",
    "ful_F",
    "rank_change_quota",
    "rank_change_family",
    "sel_change_quota",
    "sel_change_nocost",
]
# ★ 非实质字段（★ 相同也不影响判断）
NON_SUBSTANTIVE = [
    "tag", "rep", "batch_id", "topic_id", "model", "question", "seed", "arm",
    "error", "n_cand_ok", "n_cand_scored", "cand_errors", "embed_error",
    "_embed_rec", "target_base", "target_quota", "target_changed", "quota_meta",
    "calls", "elapsed",
]


def dig(rec, path):
    cur = rec
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else PRE
    if not os.path.exists(src):
        # ★ ★ 不写"找不到"就完事 ⇒ ★ 要说清【它在哪】+【为什么这里没有】+【怎么办】
        print("✘ 找不到证据文件：%s" % src)
        print("  ★ 本脚本需要【重标记前】的原始样本（★ 独立采样判据的证据）")
        print("  ★ 它属于【原始数据】，★ 在 `第四组_原始数据包.zip` 里 ⇒ ⇒ ★ 单独用代码包跑【会缺】")
        print("  ★ 三个可选解法：")
        print("    ① 解压数据包到同一目录后再跑")
        print("    ② 直接指到解包后的路径：python3 -B check_independent_samples.py <路径>")
        print("    ③ 从仓内取（★ 若你在仓内）：")
        print("       python3 -B group4_state_driven/check_independent_samples.py <路径>")
        return 2
    rows = [json.loads(l) for l in open(src, encoding="utf-8") if l.strip()]
    print("=" * 78)
    print("★ 独立采样判据（★ 记录数 vs 独立样本数）")
    print("★ 源文件：%s（%d 行）" % (src, len(rows)))
    print("=" * 78)

    from collections import defaultdict
    by = defaultdict(list)
    for r in rows:
        by[(r.get("topic_id"), r.get("rep"))].append(r)

    n_records = len(rows)
    n_independent = 0
    dup_groups = []
    for key in sorted(by, key=lambda k: (str(k[0]), k[1])):
        group = by[key]
        if len(group) == 1:
            n_independent += 1
            continue
        dup_groups.append((key, group))

    for key, group in dup_groups:
        print("\n── ★ 重复单元：题 %s / rep %s（★ %d 条记录）" % (key[0], key[1], len(group)))
        a, b = group[0], group[1]
        diffs, sames = [], []
        for f in SUBSTANTIVE:
            va, vb = dig(a, f), dig(b, f)
            if json.dumps(va, ensure_ascii=False, sort_keys=True) != \
               json.dumps(vb, ensure_ascii=False, sort_keys=True):
                diffs.append(f)
            else:
                sames.append(f)
        print("   ★ 实质字段中【不同】的：%d 项 ⇒ %s" % (len(diffs), diffs))
        print("   ★ 实质字段中【相同】的：%d 项 ⇒ %s" % (len(sames), sames))
        for f in diffs:
            print("      ★ %s:" % f)
            print("         A: %s" % (json.dumps(dig(a, f), ensure_ascii=False)[:150],))
            print("         B: %s" % (json.dumps(dig(b, f), ensure_ascii=False)[:150],))
        # ── 判定 ──
        if diffs:
            n_independent += len(group)
            print("   ⇒ ★★ 判定：**独立采样**（★ 有 %d 个实质字段不同）⇒ ⇒ ★ 计入独立样本" % len(diffs))
        else:
            n_independent += 1
            print("   ⇒ ★★ 判定：**重跑副本**（★ 实质字段全同）⇒ ⇒ ★ ★ 只计 1 个独立样本")

    print("\n" + "=" * 78)
    print("★ 记录数 = %d" % n_records)
    print("★ 独立样本数 = %d" % n_independent)
    print("★ ⇒ ⇒ " + ("★ **两者相等 ⇒ 无重复计权**" if n_records == n_independent
                        else "★ **两者不等 ⇒ 有 %d 条属重复计权**" % (n_records - n_independent)))
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
