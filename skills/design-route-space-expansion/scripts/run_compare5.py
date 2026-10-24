# -*- coding: utf-8 -*-
"""五族对比实验：用户的四道题（A1–A4）× 多臂 × 多重复。

臂清单
  A1  直调（1 次调用）
  A2  开源 ADHD 项目（**机制复现**，11 步流水线 + 汇总重写）
  A3  双轴·融合门（5 分支 → 前提审查 → 反诘 → 融合重写）
  A4  双轴·去融合门（5 分支各写完整答复 → 只选不融）
  A5a 新架构·**无核验**（只 GEN/EXTRACT/SPLIT，机械装配）   ← 控制：有没有 oracle
  A5b 新架构·**学到的策略**·有核验（依据包）                  ← 主实验
  A5c 新架构·**初始策略 w=0**·有核验                          ← 控制：学到的权重有没有用

为什么要 A5a / A5c：
  A5b 唯一接触 oracle 的操作是 VERIFY。若只报 A5b，无法区分
    (i) 架构本身更强   vs   (ii) 它拿到了别人没有的事实核验器。
  A5a 隔离 (ii)；A5c 隔离「学到的权重」是否真的有用。

新架构的认知位置（FRAME/PERSONA/模型轮换）与 A3/A4 **完全一致**，
差异只在架构机制本身 —— 这样对比才公平。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "armdeps"))

import client2 as C                       # noqa: E402
import arm3                              # noqa: E402
from creativity_lab.learnarch import run_episode  # noqa: E402
from creativity_lab.client import LLM     # noqa: E402

OUT = os.environ.get("CMP_OUT", "runs/cmp8")
os.makedirs(OUT, exist_ok=True)
PRIMARY = os.environ.get("PRIMARY_MODEL", "MiniMax-M3.1-Flash-Preview")

TOPICS4 = [
    dict(tid="A1", title="湖北 620 分选 AI 专业",
         q="湖北考生，物理类620分，想学AI，应当如何选择大学？"),
    dict(tid="A2", title="公路自行车个人赛战术",
         q="公路自行车个人比赛（无车队），单圈1.6km共计15圈，单圈由两个800m直路和两个回头弯构成，"
           "本人在大集团里处于中上等水平，该如何安排战术？"),
    dict(tid="A3", title="假期最后一天作业没动",
         q="今天是五一小长假的最后一天的18:00，明天就要上学了，我的作业还一笔没动，怎么办？"),
    dict(tid="A4", title="解读一份气质量表得分",
         q="这是一份陈会昌气质量表的最终得分：胆汁质-6，多血质23，粘液质-4，抑郁质-1。"),
]

# 单一真相源：优先读 armdeps/topics4.py；读不到就用上面这份内联副本（内容一致）
try:
    from topics4 import TOPICS4  # noqa: F401,E402
except Exception:  # pragma: no cover
    pass

# 依据包（联网独立构造，不含任何答案暗示）
EV = {}
for _i in (1, 2, 3, 4):
    _p = os.path.join(HERE, "creativity_lab", "data", "user4_q%d.json" % _i)
    if os.path.exists(_p):
        EV["A%d" % _i] = json.load(open(_p, encoding="utf-8"))["evidence"]

# ---- 模型集：本轮因 M3 持续过载(529)而固定。轴B 的设计意图是「跨 5 个不同规模档位」，
# M3 挂掉时若让它的位置自动降级到 M3.1-Flash-Preview，就会与轮换里的
# M3.1-Flash-Preview 撞档 → 轴B 的多样性被悄悄削掉一半。所以显式指定 5 个互不相同的档位。
MODELS_5 = ["MiniMax-M3.1-Flash-Preview", "MiniMax-M2.7", "MiniMax-M2.5",
            "MiniMax-M2.1", "MiniMax-M2"]
arm3.AXIS_B_MODELS = MODELS_5
# 新架构的认知位置：与 A3/A4 逐条一致
ANGLES5 = [(arm3.FRAMES[i][0], arm3.FRAMES[i][1], arm3.PERSONAS[i], arm3.AXIS_B_MODELS[i])
           for i in range(5)]

ART = ("给出一份 400 字以内、可直接执行的答复。观点明确、给出具体动作与依据，"
       "不要罗列各方观点，不要写空话。只输出答复正文。")
A2_MODEL_USED = {}


def log(d):
    with open("%s/runlog.jsonl" % OUT, "a") as f:
        f.write(json.dumps(d, ensure_ascii=False) + "\n")


def save(arm, tid, rep, text, extra=None):
    open("%s/%s_r%d_%s.md" % (OUT, tid, rep, arm), "w", encoding="utf-8").write(text or "")
    if extra is not None:
        json.dump(extra, open("%s/%s_r%d_%s.json" % (OUT, tid, rep, arm), "w"),
                  ensure_ascii=False, indent=1)


# ------------------------------------------------------------------ 旧四臂
def arm_direct(q):
    return C.chat(f"{q}\n\n{ART}", PRIMARY, 1.0, 4000, min_ok=120)


def arm_adhd(q, seed=0):
    """开源 ADHD 项目臂（**机制复现**：creativity_lab/adhd_repro.py，
    照搬 engine.ts / frames.ts / render.ts，只换传输层）。
    原版 node CLI 通道在实验当天彻底挂死（Claude Code process exited with code 1），
    保留 ADH_MODE=node 入口以便通道恢复时直接用原版。"""
    mode = os.environ.get("ADH_MODE", "repro")
    raw, used = "", ""
    if mode == "node":
        env = dict(os.environ)
        env["ANTHROPIC_BASE_URL"] = "https://api.minimaxi.com/anthropic"
        env["ANTHROPIC_API_KEY"] = C.KEY
        of = "%s/.a2_out.txt" % OUT
        try:
            with open(of, "w") as fo:
                subprocess.run(["node", "dist/cli.js", q, "--model", PRIMARY],
                               cwd=os.environ.get("ADH_REPO", "/workspace/adhd-repo"),
                               stdout=fo, stderr=subprocess.STDOUT,
                               env=env, timeout=int(os.environ.get("A2_TIMEOUT", "1200")))
            raw = re.sub(r"\x1b\[[0-9;]*m", "", open(of, encoding="utf-8", errors="ignore").read())
        except Exception as e:
            print("  A2 node err:", str(e)[:60], flush=True)
        if len(raw) < 400:
            print("  A2 node 通道不可用 → 退回 repro", flush=True)
            raw = ""
    if not raw:
        from creativity_lab.adhd_repro import run_adhd
        raw, meta = run_adhd(q, model=PRIMARY, llm=LLM(), seed=seed)
        used = "repro:" + PRIMARY
    A2_MODEL_USED[used or "none"] = A2_MODEL_USED.get(used or "none", 0) + 1
    ideas = [i[:300] for i in re.findall(r"^\s*-\s*(.+)", raw, re.M) if len(i) > 12][:24]
    a = ""
    if ideas:
        a = C.chat(f"{q}\n\n以下是若干个认知位置下产出的独立想法：\n" + "\n".join(f"- {i}" for i in ideas)
                   + f"\n\n{ART}", PRIMARY, 1.0, 4000, min_ok=120)
    return a, raw, len(ideas), used


def arm_fuse(q):
    cands = [c for c in arm3.diverge(5, workers=4, topic=q + "\n\n" + ART) if c and len(c) > 60]
    a = ""
    if len(cands) >= 2:
        deep = arm3.deep_validate(cands, topic=q)
        dec = arm3.deception_check(cands, deep, topic=q)
        a = C.chat("主题：" + q + "\n\n以下是若干个独立位置上产出的判断：\n"
                   + "\n\n---\n".join(f"[{i+1}] {c[:400]}" for i, c in enumerate(cands))
                   + "\n\n对它们差异与成立条件的分析：\n" + deep[:700]
                   + "\n\n对评价标准本身的反诘：\n" + dec[:500]
                   + f"\n\n请综合以上，{ART}", PRIMARY, 1.0, 4000, min_ok=120)
    return a, len(cands)


def arm_select(q):
    arts = []

    def _branch(i):
        fname, fp = arm3.FRAMES[i]
        m = arm3.AXIS_B_MODELS[i]
        pe = arm3.PERSONAS[i]
        p = (f"问题：{q}\n\n你现在从【{fname}】这个认知位置出发。\n{fp}\n\n设定：{pe}\n\n{ART}")
        return C.chat(p, m, 1.0, 8000, min_ok=120)

    with ThreadPoolExecutor(max_workers=4) as ex:
        for o in ex.map(_branch, range(5)):
            if o and len(o) >= 120:
                arts.append(o)
    a = ""
    if arts:
        if len(arts) == 1:
            a = arts[0]
        else:
            a = C.chat("同一个问题下有若干篇**各自独立**写成的答复：\n\n"
                       + "\n\n=====\n\n".join(f"[第{i+1}篇]\n{x}" for i, x in enumerate(arts))
                       + "\n\n请挑出**其中一篇原样输出**。判据（不要重写、不要融合、不要拼接）："
                       "① 哪一篇与常规建议最不同？② 哪一篇给出的具体判断最站得住——说清它在什么条件下成立？"
                       "③ 哪一篇最不像套话？先写 60-120 字说明，然后**原样贴出被选中那篇的全文**。",
                       PRIMARY, 1.0, 5000, min_ok=120)
    return a, arts


# ------------------------------------------------------------------ 新架构臂
def run_learnarm(q, tid, w, use_verify, seed):
    llm = LLM()
    ev = EV.get(tid, "") if use_verify else None
    if use_verify and not ev:
        return None
    rng = random.Random(seed)
    g, rew, info = run_episode(q, w, rng, ev=ev, angles=ANGLES5, budget=10,
                                explore=0.25, use_verify=use_verify, synth=True, llm=llm)
    return g, info


# ------------------------------------------------------------------ 主流程
def run_topic(T, arms, reps):
    tid, q = T["tid"], T["q"]
    for rep in range(1, reps + 1):
        for arm in arms:
            t0 = time.time()
            try:
                if arm == "A1":
                    a = arm_direct(q)
                    save(arm, tid, rep, a)
                    log(dict(tid=tid, rep=rep, arm=arm, chars=len(a), calls=1,
                             secs=round(time.time() - t0)))
                elif arm == "A2":
                    sd = 1000 * rep + int(hashlib.md5(tid.encode()).hexdigest()[:8], 16) % 97
                    a, raw, ni, a2m = arm_adhd(q, seed=sd)
                    save(arm, tid, rep, a)
                    open("%s/%s_r%d_A2raw.txt" % (OUT, tid, rep), "w").write(raw)
                    log(dict(tid=tid, rep=rep, arm=arm, chars=len(a), ideas=ni, calls=12,
                             model=a2m, secs=round(time.time() - t0)))
                elif arm == "A3":
                    a, nb = arm_fuse(q)
                    save(arm, tid, rep, a)
                    log(dict(tid=tid, rep=rep, arm=arm, chars=len(a), branches=nb, calls=8,
                             secs=round(time.time() - t0)))
                elif arm == "A4":
                    a, arts = arm_select(q)
                    save(arm, tid, rep, a)
                    json.dump(arts, open("%s/%s_r%d_A4arts.json" % (OUT, tid, rep), "w"),
                              ensure_ascii=False, indent=1)
                    log(dict(tid=tid, rep=rep, arm=arm, chars=len(a), branches=len(arts), calls=6,
                             secs=round(time.time() - t0)))
                elif arm in ("A5a", "A5b", "A5c"):
                    use_verify = arm != "A5a"
                    w = np.zeros(14)
                    if arm == "A5b":
                        w = np.array(json.load(open(
                            os.path.join(HERE, "runs", "arch_learn", "result.json"),
                            encoding="utf-8"))["w"])
                    # 种子必须可复现：Python 字符串 hash 带进程随机盐，不能直接用
                    seed = 1000 * rep + int(hashlib.md5(tid.encode()).hexdigest()[:8], 16) % 97
                    r = run_learnarm(q, tid, w, use_verify, seed=seed)
                    if r is None:
                        print(f"  [{tid} r{rep}] {arm} 跳过（依据包缺失）", flush=True)
                        continue
                    g, info = r
                    save(arm, tid, rep, info["final"])
                    if info.get("synth"):
                        open("%s/%s_r%d_%s_synth.md" % (OUT, tid, rep, arm), "w",
                             encoding="utf-8").write(info["synth"])
                    json.dump(dict(ops=info["ops"], width=info["width"], conflict=info["conflict"],
                                   n_legal=info["n_legal"], n_verify=info["n_verify"],
                                   hit=info["hit"], miss=info["miss"], fallback=info["fallback"],
                                   claims=info["claims"], verd=info["verd"]),
                              open("%s/%s_r%d_%s.json" % (OUT, tid, rep, arm), "w"),
                              ensure_ascii=False, indent=1)
                    log(dict(tid=tid, rep=rep, arm=arm, chars=len(info["final"]),
                             synth_chars=len(info.get("synth") or ""),
                             width=info["width"], conflict=info["conflict"],
                             n_verify=info["n_verify"], ops=info["ops"],
                             fallback=info["fallback"], secs=round(time.time() - t0)))
                print(f"[{tid} r{rep}] {arm} ✓ {time.time()-t0:.0f}s", flush=True)
            except Exception as e:
                print(f"[{tid} r{rep}] {arm} ERR {str(e)[:90]}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="A1,A2,A3,A4,A5a,A5b,A5c")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    arms = a.arms.split(",")
    print("臂:", arms, "｜重复:", a.reps, "｜依据包:", {k: len(v) for k, v in EV.items()}, flush=True)
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for f in [ex.submit(run_topic, T, arms, a.reps) for T in TOPICS4]:
            f.result()
    print("ALL DONE %.0f 分钟" % ((time.time() - t0) / 60), flush=True)
