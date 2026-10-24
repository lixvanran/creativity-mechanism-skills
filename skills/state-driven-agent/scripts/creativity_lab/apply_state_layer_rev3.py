#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ **接口修订 rev3 应用脚本（★ 自验证 · 第四组 2026-10-25 审阅意见 ⇒ ★ ③ `tol` 必填）**

> 落点：`creativity_lab/experiments/apply_state_layer_rev3.py`
> 目标：★ `state_layer.py` 从 rev2（`b70bfb0beb2bd591`）升级到 rev3（`c1c9224a1ed59fa8`）
> ★★ **前提：★ 手上必须是 rev2（★ sha 不符 ⇒ ⇒ 直接停，★ 不"就地改"）★★

## ★★ rev3 改什么（★ 一处，★ 语义级）
★ **`tol` 从【死参数】变成【必填关键字参数】，★ 且真正参与分组**
★ · rev2：★ 签名有 `tol`，★ 函数体【不引用它】⇒ ⇒ 实际按 `round(float(v), 12)` 分组
★ · rev3：★ `tol` 必填（★ keyword-only、★ 无默认值）⇒ ⇒ **排序后相邻差 ≤ `tol` 归一簇（★ 传递闭包）**

## ★★★ ★ 四条自保护（★ 与 rev1/rev2 同款）
★ ① **锚点唯一命中**（命中 0 或 >1 ⇒ exit 2）② **应用后 sha256 校验**（不符 ⇒ exit 1）
★ ③ **幂等**（已是 rev3 ⇒ exit 0）④ **前置 sha 校验**（不是 rev2 ⇒ exit 3）

## ★★ 为什么 `tol` 必须必填（★ 第四组 2026-10-25 给出的理由，★ 我完全同意）
★ **默认值会变** ⇒ ⇒ ★ 若 rev3 改了默认 `tol` ⇒ ⇒ ★ **所有【没显式传参】的调用点会静默改变行为**
★ ⇒ ⇒ ★ ⇒ **必填参数把这件事从【静默漂移】变成【立刻 TypeError】**
★ ⇒ ⇒ ★ ⇒ ★ **这比"哨兵默认值 + 警告"更干净：★ 警告可能被忽略，★ TypeError 不会 ★★

## ★★ 与 rev2 的【输出结构】完全一致（★ ⇒ 第四组的现有断言一条都不用改）
★ · 返回类型仍是 `List[Dict[str, Any]]` ✔
★ · 簇的顺序仍是按簇内最高分降序 ✔
★ · `members` 仍是【原索引升序】✔（★ ★ rev3 初版曾误改成"按分值降序"⇒ ⇒ 已修回 ★★）
★ · 每簇仍是 `{"kind": "tie", "members": [...], "scores": [...]}` ✔

## ★★ 第四组 2026-10-25 的三条审阅意见（★ 全部已落）
★ ① docstring 写明 `tol` 的默认值 / 单位 / 具体例子 ⇒ ✔ **【没有默认值】/ 绝对分值差 / `[0.5, 0.5+0.4e-9, 0.5+0.8e-9], tol=1e-9`**
★ ② docstring 点明【传递闭包 ⇒ 簇内首尾差【可以】超过 tol】⇒ ✔ 已点明
★ ③ `tol` 改成必填（★ 或不可能被误用的哨兵默认值）⇒ ✔ **选【必填关键字参数】（★ 比哨兵更干净）**

## ★★ 为什么还是"脚本"而不是"diff"（★ 2026-10-25 教训）
★ 第四组实测：★ 我手抄的 diff【hunk 头被截断】⇒ ⇒ `git apply` 报 `corrupt patch`
★ ⇒ ⇒ ★ **⇒ "用 diff 代替全文"只换了抄的对象，★ 漏洞没堵** ⇒ ⇒ ★ **⇒ 真正堵住的是【输出可被 sha256 证伪】**
★ ⇒ ⇒ ★ ★ **⇒ 而本脚本里嵌的 rev3 全文是【从 rev3 文件自动提取】的（★ 不是手抄）⇒ ⇒ ★ ⇒ 仓内文件与脚本输出【逐字节一致】★★
"""

import hashlib
import os
import sys

TARGET = "creativity_lab/state_layer.py"
EXPECT_SHA = "c1c9224a1ed59fa8"      # ★ rev3 目标 sha
OLD_SHA = "b70bfb0beb2bd591"      # ★ rev2 起点 sha
REV2_SHA = "b70bfb0beb2bd591"     # ★ rev2（★ 与 OLD_SHA 同值，★ 留作语义标注）

OLD_ANCHOR = "def detect_tie(scores: List[float], tol: float = 1e-9) -> List[Dict[str, Any]]:"

NEW_BLOCK = 'def detect_tie(scores: List[float], *, tol: float) -> List[Dict[str, Any]]:\n    """★ **并列检测**（★ 第四组 2026-10-25 提出 ⇒ ★ 裁决：★ 接口层提供能力，★ 接线由第四组做）\n\n    ★ **为什么放在接口层**：★ 「两个候选评分并列 ⇒ 它们是合法分歧」是【规则的一部分】，\n    ★ ★ **不该靠调用方记得去调 `preserve_divergence`** ⇒ ⇒ ★ 否则接线时一漏，分歧语义就丢了\n    ★ ★（★ 第四组已报告：★ 他们的 `Select(greedy)` 【会吃掉并列】⇒ ⇒ ★ 这正是必须补的一步）\n\n    ★★★ **★ rev2 修正（★ 第四组 2026-10-25 实测发现 ⇒ ★ ① 只查最大值处漏检中位并列）**：\n    ★ ★ **原实现只找【最高分处】的并列 ⇒ ⇒ `detect_tie([0.9, 0.5, 0.5])` 返回 None**\n    ★ ⇒ ⇒ **⇒ 但「合法分歧」【未必只发生在最高分】⇒ ⇒ 来自不同来源的【第二名并列】也是真实意见分歧**\n    ★ ⇒ ⇒ ★★ **⇒ 改法：★ 返回【所有】并列簇（★ 不只最大簇）★ ⇒ 且返回类型从单个 dict 改成 List**\n\n    ★★★ **★ rev3 修正（★ 第四组 2026-10-25 审阅意见 ⇒ ★ ③ `tol` 必须是必填）★★**\n    ★ ★★ **rev2 的 `tol` 是【死参数】（★ 签名有、函数体不引用 ⇒ ⇒ 实际按 `round(v, 12)` 分组）★★**\n    ★ ⇒ ⇒ ★★ **rev3：★ `tol` 变成【必填关键字参数】（★ keyword-only、★ 无默认值）★★**\n    ★ ⇒ ⇒ ★★ **★ 为什么必须这样（★ 第四组给出的理由，★ 我完全同意）★★**\n    ★ ★ **默认值会变** ⇒ ⇒ ★ 若 rev3 改了默认 `tol` ⇒ ⇒ ★ **所有【没显式传参】的调用点会静默改变行为**\n    ★ ⇒ ⇒ ★ ⇒ ★ **★ 必填参数把这件事从【静默漂移】变成【立刻 TypeError】★★**\n    ★ ⇒ ⇒ ★ ★ **★ 这比"哨兵默认值 + 警告"更干净：★ 警告可能被忽略，★ TypeError 不会 ★★\n    ★ ⇒ ⇒ ★ ★ **（★ 第四组说要在他们那边加"禁止不传 tol"的守卫断言 ⇒ ⇒ ★ ★ ⇒ ★ ★ **必填参数让那条断言变得多余** ★）★\n\n    ★★★ **★★ rev3 的分组规则（★ 写死，★ 第四组照此补断言）★★**\n    ★ **① `tol` 的默认值**：★ **没有默认值**（★ 必填关键字参数 ⇒ ⇒ ★ 漏传 ⇒ `TypeError`）\n    ★ **② `tol` 的单位**：★ **绝对分值差**（★ 与 `scores` 同量纲 ⇒ ⇒ ★ 典型取 `1e-9`）\n    ★ **③ 分组算法**：★ **排序后相邻差 ≤ `tol` ⇒ ⇒ 归入同一簇（★ 传递闭包：★ 一趟扫描）**\n    ★ ⇒ ⇒ ★ **举例**（★ 第四组点名要"带小数点后 10 位"的那种）：\n    ★ \u3000 `detect_tie([0.5, 0.5 + 0.4e-9, 0.5 + 0.8e-9], tol=1e-9)`\n    ★ \u3000 ⇒ ⇒ **三值全归一簇**（★ 相邻差 0.4e-9、0.4e-9 都 ≤ 1e-9）⇒ ⇒ **返回 1 个簇，members=[0,1,2]**\n    ★ \u3000 ⇒ ⇒ ★ ★ **★ 【边界特性，★ 别踩】★★**\n    ★ \u3000 ⇒ ⇒ **该簇的【首尾差 = 0.8e-9】⇒ ⇒ ⇒ ⇒ ★ ★ `tol` 【不是】"簇内最大跨度"★★**\n    ★ \u3000 ⇒ ⇒ **★ 传递闭包 ⇒ ⇒ 簇内首尾差【可以】超过 `tol` ⇒ ⇒ ⇒ ⇒ ★ ⇒ **故 `tol` 的正确读法是\n    ★ \u3000\u3000\u3000"相邻两值被判为同一簇的【最大间隔】"，★ 不是"同一簇内任意两值的最大距离" ★★\n    ★ \u3000 ⇒ ⇒ ★ ★ **（★ 第四组要求在 docstring 里点明这一点 ⇒ ⇒ ★ ⇒ 【已点明】★★）★\n\n    ★ ★★ **★ rev2 → rev3 的行为差异（★ 第四组要据此改断言）★★**\n    ★ · rev2 按 `round(float(v), 12)` 分组 ⇒ ⇒ **差值 < 1e-12 的判为并列，≥ 1e-12 的不判**\n    ★ · rev3 按 `tol` 分组（★ 排序 + 相邻差）⇒ ⇒ **差值 ≤ `tol` 的判为并列**\n    ★ ⇒ ⇒ ★ **★ 具体地：★ `tol=1e-9` 时，★ 差 1e-10 的两个分值 ★ **rev2 判为并列、rev3 也判为并列**；\n    ★ \u3000 但差 1e-13 的两个分值 ★ **rev2 判为并列、rev3（tol=1e-9）也并列**；★\n    ★ \u3000 ★ **而差 5e-13 的两个分值：★ rev2 判为并列（round 到 12 位后相同）★ ⇒ ⇒ ★ rev3 也并列（5e-13 ≤ 1e-9）★★\n    ★ ⇒ ⇒ ★ ★★ **★ ⇒ 关键差异【只在 `tol` 远小于 1e-12 时才出现】：★ `tol=1e-13` 时，\n    ★ \u3000 差 5e-13 的两个分值 ★ **rev2 并列、rev3 不并列** ⇒ ⇒ ★ ⇒ **★ 这就是"必须显式传 tol"的现实理由 ★★**\n\n    ★ **返回**：★ ★ **List of clusters**，每簇 `{"kind": "tie", "members": [...], "scores": [...]}`；\n    ★ 无任何并列 ⇒ 返回 **空列表 `[]`**（★ ★ 不是 None —— ★ 空列表更安全，★ 调用方不必判 None）\n    ★ ★ **簇的顺序**：★ **按簇内最高分从高到低**（★ 稳定 ⇒ ⇒ 同一输入恒定输出）\n    ★ ★ **簇内 `members` 的顺序**：★ **按【原索引升序】**（★ ★ 与 rev2 完全一致 ⇒ ⇒ 第四组已照现状写的断言【不用改】★★）\n    ★ ★ **对应的 `scores` 与 `members` 同序**（★ 即 `scores[i]` 是第 i 个成员自己的分值）\n    ★ ★ **本函数【不修改状态】** ⇒ ⇒ ★ 接线方式由调用方决定（★ 通常是：\n    ★ `for d in detect_tie(scores, tol=1e-9): st = preserve_divergence(st, d)`）\n    ★ ★ ★ **★ 接线侧硬要求（★ 第四组 2026-10-25 明确提出）★**\n    ★ ★ **所有调用点【必须显式传 `tol=`]** ⇒ ⇒ ★ **不许用默认值** ⇒ ⇒ ★\n    ★ ★ **★ 理由：★ 默认值会随接口版本变 ⇒ ⇒ ★ ⇒ 未显式传参的调用点会静默改变行为 ⇒ ⇒ ★ ⇒ 读数会漂 ★★\n\n    ★★★ **★ 返回类型不变（★ 第四组确认：★ 你们的探针按"簇数"判检出 ⇒ ⇒ ★ ★ 不用改）★★**\n    ★ ★★ `members` / `scores` 的结构不变（★ 仍是 `{"kind":"tie","members":[...],"scores":[...]}`）★★\n    """\n    if not scores:\n        return []\n    # ★ ★ 按【分值排序】⇒ ⇒ 再用【相邻差 ≤ tol】切簇（★ 传递闭包：★ 一趟扫描）\n    order = sorted(range(len(scores)), key=lambda i: float(scores[i]))\n    groups: List[List[int]] = []\n    cur: List[int] = [order[0]]\n    for i in order[1:]:\n        if float(scores[i]) - float(scores[cur[-1]]) <= tol:\n            cur.append(i)\n        else:\n            groups.append(cur)\n            cur = [i]\n    groups.append(cur)\n    out: List[Dict[str, Any]] = []\n    for g in groups:\n        if len(g) < 2:\n            continue\n        # ★ 簇内按【原索引升序】（★ rev2 口径 ⇒ ⇒ 第四组已照现状写的断言不用改）\n        g_asc = sorted(g)\n        out.append({"kind": "tie", "members": g_asc,\n                    "scores": [scores[i] for i in g_asc]})\n    # ★ 簇间按【簇内最高分】从高到低（★ 稳定排序 ⇒ ⇒ 同一输入恒定输出）\n    out.sort(key=lambda d: max(d["scores"]), reverse=True)\n    return out'


def sha_of(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def main():
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    p = os.path.join(root, TARGET)
    if not os.path.isfile(p):
        print("✘ 找不到 %s" % p)
        return 2
    cur = sha_of(p)
    if cur == EXPECT_SHA:
        print("✔ 已是 rev3（★ sha %s）⇒ 幂等退出" % cur)
        return 0
    if cur != OLD_SHA:
        print("✘ 起点 sha = %s，★ 期望 rev2 = %s（★ 或已是 rev3 = %s）⇒ ⇒ 【不就地改】" % (cur, OLD_SHA, EXPECT_SHA))
        return 3
    with open(p, encoding="utf-8") as f:
        s = f.read()
    n = s.count(OLD_ANCHOR)
    if n != 1:
        print("✘ 锚点命中 %d 次（★ 应为 1）⇒ ⇒ 停止" % n)
        return 2
    # ★ 定位旧整块（★ 从锚点行到下一个顶层 def）
    i = s.index(OLD_ANCHOR)
    j = s.index("def preserve_divergence", i)
    s2 = s[:i] + NEW_BLOCK + "\n\n\n" + s[j:]
    with open(p, "w", encoding="utf-8") as f:
        f.write(s2)
    got = sha_of(p)
    if got != EXPECT_SHA:
        print("✘ 应用后 sha = %s，★ 期望 %s ⇒ ⇒ 【已回滚】" % (got, EXPECT_SHA))
        with open(p, "w", encoding="utf-8") as f:
            f.write(s)
        return 1
    print("✔ rev2 → rev3 应用成功（★ sha %s ⇒ %s）" % (OLD_SHA, got))
    print("★ 接线侧：★ 所有 detect_tie 调用点【必须显式传 tol=】")
    print("      for d in detect_tie(scores, tol=1e-9): st = preserve_divergence(st, d)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
