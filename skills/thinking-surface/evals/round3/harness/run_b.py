# -*- coding: utf-8 -*-
"""run_b.py —— 路 B 的跑批（★ 真实题 + 外部金标 ★）

★ 三臂：B0 基线 / B1 skill v1 / B2 skill v2
★ 阶段：PLAN（选轴/列实体）→ GEN（4 次隔离生成）→ MERGE（保留分歧合流）
★ 失败可计数、★ 增量落盘（★ 沙箱会清长跑 ★）、★ 不静默归零
"""
from __future__ import annotations
import argparse, json, os, sys, threading, time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import arms_b
import parse_b

# ★ 双通道：★ minimax = 与 Round 1/2 同模型（★ 可跨批次比 ★）
#            openrouter = ★ 跨厂商复现（★ MiniMax 配额枯竭时的备用、★ 也用于检验「跨模型断言」★）
BACKEND = os.environ.get("RB_BACKEND", "minimax")
if BACKEND == "openrouter":
    import openrouter_client as client
    MODEL = os.environ.get("RB_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")
else:
    import client
    MODEL = os.environ.get("RB_MODEL", "MiniMax-M2.7")
TEMP = float(os.environ.get("RB_TEMP", "0.7"))
MAXTOK = int(os.environ.get("RB_MAXTOK", "1600"))
_lock = threading.Lock()


def atomic_jsonl(path, rows):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)


class Store:
    def __init__(self, path):
        self.path = path
        self.rows = []
        if os.path.exists(path):
            for line in open(path, encoding="utf-8"):
                line = line.strip()
                if line:
                    try: self.rows.append(json.loads(line))
                    except Exception: pass
        self.done = {(r["phase"], r["arm"], r["topic"], r["rep"], r["unit"]) for r in self.rows}

    def write(self, rec):
        with _lock:
            self.rows.append(rec)
            atomic_jsonl(self.path, self.rows)


def call(store, phase, arm, topic, rep, unit, content, max_tokens=None):
    key = (phase, arm, topic, rep, unit)
    if key in store.done:
        return None
    t0 = time.time()
    try:
        r = client.chat([{"role": "user", "content": content}],
                        model=MODEL, temperature=TEMP,
                        max_tokens=max_tokens or MAXTOK)
        ok = bool(r.get("ok")); text = r.get("text") or ""
        usage = r.get("usage") or {}
        extra = {k: r.get(k) for k in ("finish_reason", "truncated", "failure_kind", "error")
                 if r.get(k) is not None}
    except Exception as e:
        ok, text, usage = False, "", {}
        extra = {"error": "%s: %s" % (type(e).__name__, str(e)[:120])}
    rec = {"phase": phase, "arm": arm, "topic": topic, "rep": rep, "unit": unit,
           "ok": ok, "text": text, "chars": len(text or ""),
           "usage": usage, "sec": round(time.time() - t0, 1), "model": MODEL,
           "at": time.time()}
    rec.update(extra)
    store.write(rec)
    return rec


def call_json(store, phase, arm, topic, rep, unit, content):
    key = (phase, arm, topic, rep, unit)
    if key in store.done:
        return None
    t0 = time.time()
    try:
        r = client.json_call([{"role": "user", "content": content}],
                             model=MODEL, temperature=TEMP, max_tokens=2600,
                             thinking="disabled")
        ok = bool(r.get("ok")); data = r.get("parsed")
        extra = {k: r.get(k) for k in ("parse_error", "error") if r.get(k) is not None}
    except Exception as e:
        ok, data = False, None
        extra = {"error": "%s: %s" % (type(e).__name__, str(e)[:120])}
    rec = {"phase": phase, "arm": arm, "topic": topic, "rep": rep, "unit": unit,
           "ok": ok, "parsed": data,
           "text": json.dumps(data, ensure_ascii=False) if data else "",
           "sec": round(time.time() - t0, 1), "model": MODEL, "at": time.time()}
    rec.update(extra)
    store.write(rec)
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "..", "runs", "b1"))
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--arms", default="B0,B1,B2")
    ap.add_argument("--backend", default=os.environ.get("RB_BACKEND", "minimax"))
    ap.add_argument("--model", default=os.environ.get("RB_MODEL", ""))
    args = ap.parse_args()
    global BACKEND, MODEL
    BACKEND = args.backend
    if args.model:
        MODEL = args.model
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    store = Store(os.path.join(out, "calls.jsonl"))
    topics = json.load(open(os.path.join(HERE, "..", "topics.json"), encoding="utf-8"))
    arms_on = set(args.arms.split(","))

    def plan_job(arm, t, rep):
        u = arms_b.p_skillv1_plan(t) if arm == "B1" else arms_b.p_skillv2_plan(t)
        call_json(store, "PLAN", arm, t["id"], rep, "plan", u)

    def gen_job(arm, t, rep, idx, parsed):
        paths = (parsed or {}).get("paths") or []
        paths = [p for p in paths if isinstance(p, dict) and (p.get("rewrite") or "").strip()]
        if not paths:
            store.write({"phase": "GEN", "arm": arm, "topic": t["id"], "rep": rep,
                         "unit": "b%d" % idx, "ok": False, "text": "", "parsed": None,
                         "chars": 0, "sec": 0, "model": MODEL, "at": time.time(),
                         "failure_kind": "plan_unusable"})
            return
        if idx >= len(paths):
            return
        p = paths[idx]
        call(store, "GEN", arm, t["id"], rep, "b%d" % idx,
             arms_b.p_branch(t, p.get("rewrite"), p.get("signature") or []))

    def merge_job(arm, t, rep, texts):
        if not texts:
            return
        call(store, "MERGE", arm, t["id"], rep, "m",
             arms_b.p_merge(t, texts), max_tokens=2400)

    jobs = []
    for t in topics:
        for rep in range(args.reps):
            if "B0" in arms_on:
                jobs.append(("B0", t, rep))
            if "B1" in arms_on:
                jobs.append(("B1", t, rep))
            if "B2" in arms_on:
                jobs.append(("B2", t, rep))

    def plan_with_retry(arm, t, rep, prompt_fn, unit_prefix="plan"):
        """★ 规划 + 结构校验 + 不足则重规划一次（★ 绝不补造数据 ★）"""
        r = call_json(store, "PLAN", arm, t["id"], rep, unit_prefix, prompt_fn(None))
        parsed = (r or {}).get("parsed")
        paths, flag = parse_b.extract_paths(parsed, (r or {}).get("text"))
        if len(paths) < 3:
            # ★ 重规划一次（★ strict 提示 ★）
            r2 = call_json(store, "PLAN", arm, t["id"], rep, unit_prefix + "_retry",
                           arms_b.with_strict(prompt_fn(None)))
            p2, f2 = parse_b.extract_paths((r2 or {}).get("parsed"), (r2 or {}).get("text"))
            if len(p2) >= 3:
                parsed, paths, flag = (r2 or {}).get("parsed"), p2, "retry_" + f2
        store.write({"phase": "PLANNOTE", "arm": arm, "topic": t["id"], "rep": rep,
                     "unit": unit_prefix, "ok": len(paths) >= 3, "n_paths": len(paths),
                     "flag": flag, "chars": 0, "sec": 0, "model": MODEL, "at": time.time(),
                     "failure_kind": None if len(paths) >= 3 else "plan_too_few_paths"})
        return parsed, paths

    def do(job):
        arm, t, rep = job
        if arm == "B0":
            call(store, "BASE", arm, t["id"], rep, "u0", arms_b.p_base(t), max_tokens=2400)
            return
        if arm == "B1":
            parsed, paths = plan_with_retry(arm, t, rep, lambda _x: arms_b.p_skillv1_plan(t))
        else:
            # ★ v2：★ 第 0 步先自举实体类别（★ 单独一次调用 ★）
            re_ = call_json(store, "ENT", arm, t["id"], rep, "ent",
                            arms_b.p_skillv2_entities(t))
            cats, cflag = parse_b.extract_entities((re_ or {}).get("parsed"), (re_ or {}).get("text"))
            store.write({"phase": "ENTNOTE", "arm": arm, "topic": t["id"], "rep": rep,
                         "unit": "ent", "ok": bool(cats), "n_entities": len(cats),
                         "flag": cflag, "chars": 0, "sec": 0, "model": MODEL, "at": time.time(),
                         "failure_kind": None if cats else "no_entities"})
            ents_text = "\n".join("- %s：%s" % (c.get("category"), "、".join(c.get("examples") or [])[:80])
                                   for c in cats) or "（未能列出）"
            parsed, paths = plan_with_retry(
                arm, t, rep, lambda _x: arms_b.p_skillv2_plan(t, ents_text))
        if not paths or len(paths) < 3:
            return          # ★ 规划不足 ⇒ 该 rep 无产出（★ 显式记录在 PLANNOTE ★）
        # 4 次隔离生成（★ 顺序执行以免互相污染上下文 ★）
        texts = []
        for i in range(4):
            g = gen_job(arm, t, rep, i, {"paths": paths})
            if g and g.get("ok"):
                texts.append(g["text"])
        merge_job(arm, t, rep, texts)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(do, j) for j in jobs]
        for i, f in enumerate(futs):
            f.result()
            if (i + 1) % 5 == 0:
                print("  progress %d/%d | records=%d" % (i + 1, len(futs), len(store.rows)), flush=True)
    print("DONE records=%d" % len(store.rows))


if __name__ == "__main__":
    main()
