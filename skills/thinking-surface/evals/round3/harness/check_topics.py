"""路 B 防泄题闸门（★ pre-flight、★ 跑之前必须全绿 ★）

★ 与 Round 1 的闸门同族、但判据不同：★ 这里防的是【维度关键词泄进题面】★★
★ 泄漏后果：★ 模型只要把题面里的词抄一遍就能覆盖该维度 ⇒ 测出来的是自证 ★

检查项：
  R1  题面不得出现任一维度的任一 must 词（★ 防泄题 ★）
  R2  各维度的 must 词【不得完全相同】（★ 互含允许、★ 由最长优先匹配消歧 ★）
  R3  每维度 must 词数 >= 2（★ 否则命中阈值无意义 ★）
  R4  跨域词不得与任何 must 词重叠（★ 跨域词是"无效"标记、★ 不是维度证据 ★）
  R5  题数与每题轴数符合预注册

退出码：0 全绿；1 有红。
"""
from __future__ import annotations
import json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOPICS = HERE.parent / "topics.json"
EXPECT_N = 1
EXPECT_AXES = 10
MIN_MUST = 2

def load(path=TOPICS):
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]

def check(topics):
    errs = []
    if len(topics) != EXPECT_N:
        errs.append("R5 题数 %d != 预注册 %d" % (len(topics), EXPECT_N))
    for t in topics:
        axes = t.get("axes") or []
        if len(axes) != EXPECT_AXES:
            errs.append("R5 %s 轴数 %d != %d" % (t["id"], len(axes), EXPECT_AXES))
        # R1 题面泄题
        for ax in axes:
            for w in ax["must"]:
                if w in t["prompt"]:
                    errs.append("R1 ★题面泄题★ %s %s 泄出 %r" % (t["id"], ax["id"], w))
        # ★ R2b：★ 题面不得出现跨域词（★ 跨域词是"无效"标记、★ 题面出现会让它变成"该提的" ★）
        # R2 跨维度重叠
        for i, a in enumerate(axes):
            for b in axes[i+1:]:
                for wa in a["must"]:
                    for wb in b["must"]:
                        # ★ 只禁【完全相同】；★ 互含改为允许、★ 由【最长优先匹配】消歧 ★
                        # （★ 依据：★ "城市" ⊂ "香港城市大学" 天然存在、★ 删词会伤维度完整性 ★）
                        if wa and wa == wb:
                            errs.append("R2 %s/%s must 完全相同: %r" % (a["id"], b["id"], wa))
        for w in (t.get("offdomain") or []):
            if w in t["prompt"]:
                errs.append("R2b ★题面含跨域词★ %s %r" % (t["id"], w))
        # R3 词数
        for ax in axes:
            if len(ax["must"]) < MIN_MUST:
                errs.append("R3 %s must 词数 %d < %d" % (ax["id"], len(ax["must"]), MIN_MUST))
        # R4 跨域词污染
        for w in (t.get("offdomain") or []):
            for ax in axes:
                for wa in ax["must"]:
                    if wa and (wa in w or w in wa):
                        errs.append("R4 跨域词 %r 与 %s 的 must %r 重叠" % (w, ax["id"], wa))
    return errs

if __name__ == "__main__":
    ts = load()
    errs = check(ts)
    if errs:
        print("✘ 闸门未过（%d 项）：" % len(errs))
        for e in errs: print("   -", e)
        sys.exit(1)
    print("✔ 路 B 防泄题闸门全绿：%d 题 / %d 维" % (len(ts), sum(len(t["axes"]) for t in ts)))
