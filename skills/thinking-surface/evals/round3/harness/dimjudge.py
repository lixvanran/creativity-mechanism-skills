# -*- coding: utf-8 -*-
"""dimjudge.py —— 路 B 的判据：★ 缺席率（★ 外部金标口径 ★）

★★ 核心口径（★ 事前定死、★ 跑之前写进预注册 ★）★★
1. 【最长优先匹配】：★ 一个文本位置若同时命中长短两个词、★ 只计长的 ★
   ★ 理由：★ "城市" ⊂ "香港城市大学" ⇒ 不消歧则【一个词同时算两维证据】⇒ 覆盖被污染 ★
2. 【覆盖】：★ 该维度命中 ≥ ceil(2/3 × 词数) 个 must 词、★ 且 0 个 forbid 词命中 ★
   （★ 与 Round 1 的 axis_hits 同族、★ 阈值一致 ★）
3. 【缺席率】：★ (未覆盖维度数 / 总维度数) ★  ← ★ 主指标 ★
4. 【跨域率】：★ 出现 offdomain 词的比例（★ "进大厂"这类跨域分支 ★）
5. 【自举召回率】：★ skill 自举的实体类别 ∩ 外部金标维度 / 外部金标维度 ★
   ★ 意义：★ 这条读数【不需要外部清单也能算】（★ 用自举表当分母 ★）
   ⇒ ⇒ skill 的"缺席自检"因此可以【自洽运行】★
"""
from __future__ import annotations
import re


def _hits(text, words):
    """★ 最长优先匹配 ⇒ 返回命中的词集合 ★"""
    occupied = []          # 已占用的字符区间
    hit = set()
    for w in sorted(set(words), key=len, reverse=True):
        if not w:
            continue
        for m in re.finditer(re.escape(w), text):
            span = (m.start(), m.end())
            if any(not (span[1] <= o[0] or span[0] >= o[1]) for o in occupied):
                continue                       # ★ 已被更长词占用 ⇒ 跳过 ★
            occupied.append(span)
            hit.add(w)
            break                              # ★ 每个词只计一次 ★
    return hit


def axis_hit(axis, text):
    must = axis.get("must") or []
    forbid = axis.get("forbid") or []
    if not must:
        return {"hit": False, "n_must": 0, "need": 0, "must_hit": [], "forbid_hit": []}
    need = -(-len(must) * 2 // 3)            # ★ ceil(2/3 × 词数) ★
    mh = _hits(text, must)
    fh = _hits(text, forbid)
    return {"hit": (len(mh) >= need and not fh), "n_must": len(must), "need": need,
            "must_hit": sorted(mh), "forbid_hit": sorted(fh)}


def coverage(topic, text):
    """★ 返回 (覆盖的维度 id 列表, 每维明细) ★"""
    detail = {}
    for ax in topic["axes"]:
        detail[ax["id"]] = axis_hit(ax, text)
    covered = [k for k, v in detail.items() if v["hit"]]
    return covered, detail


def absent_rate(topic, text):
    """★ 缺席率 = 未覆盖维度数 / 总维度数（★ 缺席率 = 1 − 覆盖率 ★）"""
    n = len(topic["axes"])
    cov, _ = coverage(topic, text)
    return (n - len(cov)) / n if n else 0.0, cov


def offdomain_hit(topic, text):
    return [w for w in (topic.get("offdomain") or []) if w in text]


def entity_hits(text):
    """★ 库驱动的真实校名命中（★ 幻觉检测的原料 ★）"""
    import schools
    return sorted({s for s in schools.KNOWN_CANON if s and s in text})
