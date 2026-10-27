"""题集防漏检查器（pre-flight，实验跑之前必须全绿）。

要防的漏洞：**评分用的关键词（must / forbid）出现在喂给实验臂的文本里**。
这会让实验臂「拿到答案」——它只要把评分词抄进输出就能得分，测出来的就是自证。
这属于「校验对象 ≠ 人改对象」和「判据与被测对象同源」两种坑的合体。

检查项：
  L1  每条轴的 feed 文本里，不得出现该轴的任一 must / forbid 子串
  L2  每条轴的 feed 文本里，不得出现【其它轴】的任一 must 子串（跨轴串味也会送答案）
  L3  题目 prompt 里，不得出现任一轴的任一 must 子串
  L4  must 词互不包含（避免「选书」和「书目」这类互相包含导致阈值失效）
  L5  forbid 词不得与本轴 must 词重叠
  L6  每轴 must 词数 >= 2（否则命中阈值无意义）
  L7  题数、每题轴数、题型分布符合预注册

退出码：0 全绿；1 有红（打印每条红项）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOPICS = HERE / "topics.jsonl"

# 预注册的题集口径（改动必须同步改预注册文件）
EXPECT_N_TOPICS = 7
EXPECT_OPEN_TOPICS = 6
EXPECT_AXES_PER_OPEN = 5
MIN_MUST = 2


def load_topics(path: Path = TOPICS):
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def check(topics) -> list[str]:
    errs: list[str] = []
    if len(topics) != EXPECT_N_TOPICS:
        errs.append(f"L7 题数 {len(topics)} != 预注册 {EXPECT_N_TOPICS}")
    open_topics = [t for t in topics if t.get("type") == "open"]
    if len(open_topics) != EXPECT_OPEN_TOPICS:
        errs.append(f"L7 开放题数 {len(open_topics)} != 预注册 {EXPECT_OPEN_TOPICS}")

    for t in topics:
        tid = t.get("id", "?")
        axes = t.get("axes", [])
        if t.get("type") == "open" and len(axes) != EXPECT_AXES_PER_OPEN:
            errs.append(f"L7 {tid} 开放题轴数 {len(axes)} != 预注册 {EXPECT_AXES_PER_OPEN}")
        all_musts = [m for a in axes for m in a.get("must", [])]
        for a in axes:
            aid = a.get("id", "?")
            feed = a.get("feed", "") or ""
            must = a.get("must", []) or []
            forbid = a.get("forbid", []) or []
            if len(must) < MIN_MUST:
                errs.append(f"L6 {aid} must 词数 {len(must)} < {MIN_MUST}")
            # L1
            for w in must + forbid:
                if w and w in feed:
                    errs.append(f"L1 {aid} feed 含本轴评分词 {w!r}")
            # L2 跨轴
            for b in axes:
                if b.get("id") == aid:
                    continue
                for w in b.get("must", []) or []:
                    if w and w in feed:
                        errs.append(f"L2 {aid} feed 含其它轴 {b.get('id')} 的评分词 {w!r}")
            # L3 题面
            for w in all_musts:
                if w and w in (t.get("prompt", "") or ""):
                    errs.append(f"L3 {tid} 题面含评分词 {w!r}")
            # L4 must 互不包含
            for i, w1 in enumerate(must):
                for w2 in must[i + 1:]:
                    if w1 in w2 or w2 in w1:
                        errs.append(f"L4 {aid} must 词互含 {w1!r} / {w2!r}")
            # L5 forbid 与 must 重叠
            for w1 in forbid:
                for w2 in must:
                    if w1 and w2 and (w1 in w2 or w2 in w1):
                        errs.append(f"L5 {aid} forbid {w1!r} 与 must {w2!r} 语义重叠")
    return errs


def main() -> int:
    topics = load_topics()
    errs = check(topics)
    if errs:
        print(f"FAIL: {len(errs)} 项查漏未过")
        for e in errs:
            print("  -", e)
        return 1
    n_axes = sum(len(t.get("axes", [])) for t in topics)
    print(f"OK: {len(topics)} 题 / {n_axes} 轴，无评分词泄漏")
    return 0


if __name__ == "__main__":
    sys.exit(main())
