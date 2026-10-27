# -*- coding: utf-8 -*-
"""parse_b.py —— 规划输出的【宽容解析 + 结构校验】★★

★ 实测到的两类真实失败（★ nemotron 在 response_format 下仍会结构不严 ★）：
  F1 「摊平」：{"paths":[{...}], "axis":"X", "rewrite":"...", ...} ⇒ 第 2..N 条路径被写到顶层
  F2 「不成数组」：{"category":"目标院校","examples":[...]} ⇒ 单个对象、没包成数组

★ 处置原则（★ 事先定死 ★）：
  1. 先 json.loads；★ 失败 ⇒ 尝试从原文抠 JSON 片段
  2. 结构不对 ⇒ 【不补造】⇒ 先尝试【从原文重建】（★ 重建要记 flag ★）
  3. 重建后仍不足 3 条 ⇒ 【交由调用方重规划】⇒ 仍不足 ⇒ 该 rep 记失败（★ 失败不静默归零 ★）
"""
from __future__ import annotations
import json, re

_OBJ = re.compile(r"\{.*\}", re.S)


def _loads_any(text):
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    m = _OBJ.search(text)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return None


def _as_list(x):
    if x is None:
        return []
    if isinstance(x, list):
        return [i for i in x if isinstance(i, dict)]
    if isinstance(x, dict):
        return [x]
    return []


def extract_paths(parsed, raw_text=None):
    """★ 返回 (paths, flag) ★ flag ∈ ok | rebuilt | empty ★"""
    paths = _as_list((parsed or {}).get("paths"))
    if len(paths) >= 3:
        return paths[:4], "ok"
    # ★ F1 摊平重建：★ 顶层若出现了路径字段、★ 把它并进 paths ★
    if parsed and isinstance(parsed, dict):
        flat = {}
        for k in ("axis", "rewrite", "signature", "antisignature", "cost", "source", "grounded_in"):
            if k in parsed:
                flat[k] = parsed[k]
        if flat.get("rewrite"):
            paths = paths + [flat]
    # ★ 再从原文抠（★ 应对"多个并列 JSON 对象"★）
    if len(paths) < 3 and raw_text:
        for m in re.finditer(r'"rewrite"\s*:\s*"((?:[^"\\]|\\.)*)"', raw_text):
            frag = m.group(0)
            start = raw_text.rfind("{", 0, m.start())
            if start < 0:
                continue
            depth, end = 0, None
            for i in range(start, len(raw_text)):
                if raw_text[i] == "{":
                    depth += 1
                elif raw_text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            if end:
                try:
                    o = json.loads(raw_text[start:end])
                except Exception:
                    continue
                if isinstance(o, dict) and o.get("rewrite") and o not in paths:
                    paths.append(o)
    paths = [p for p in paths if p.get("rewrite")][:4]
    if len(paths) >= 3:
        return paths, "rebuilt"
    return paths, "empty"


def extract_entities(parsed, raw_text=None):
    """★ 返回 (categories, flag) ★"""
    cats = _as_list((parsed or {}).get("entities")) or _as_list((parsed or {}).get("categories"))
    if not cats and isinstance(parsed, dict) and parsed.get("category"):
        cats = [parsed]
    if not cats and raw_text:
        for m in re.finditer(r'"category"\s*:\s*"((?:[^"\\]|\\.)*)"', raw_text):
            frag = raw_text[max(0, m.start() - 200): m.end() + 400]
            mm = re.search(r'"examples"\s*:\s*\[(.*?)\]', frag, re.S)
            ex = re.findall(r'"((?:[^"\\]|\\.)*)"', mm.group(1)) if mm else []
            cats.append({"category": m.group(1), "examples": ex})
    return cats, ("ok" if cats else "empty")
