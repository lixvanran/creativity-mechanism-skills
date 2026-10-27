"""跑批器。

结构：分阶段、每阶段扁平并行。
  Phase MAP  —— 只有 A3 需要：任务 → 决策点地图
  Phase GEN  —— 生成各臂输出
  Phase AUD  —— 兑现率审计（只对有 brief 的单元）
  Phase SKL  —— 机制骨架抽取（对所有输出）
  Phase HEALTH—— 判官健康度：用另一个模型重跑 10% 抽样，比一致率

纪律：
- 每条调用即时追加落盘（JSONL），可断点续跑；
- manifest 记「应有多少」，收尾核对「实有多少」，不一致就响亮报错（不静默归零）；
- 失败/空/截断单独计数，读数里显示 N，不显示 0。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import arms  # noqa: E402
import client  # noqa: E402
from check_topics import load_topics  # noqa: E402
from irrelevant import IRRELEVANT_LENSES  # noqa: E402

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"
MODEL_GEN = "MiniMax-M2.7"
MODEL_JUDGE = "MiniMax-M2.7"
MODEL_JUDGE2 = "MiniMax-M3"  # 判官健康度对照模型
TEMP_GEN = 0.7
TEMP_MAP = 0.6
MAXTOK_GEN = 3000
MAXTOK_JSON = 4000
MAXTOK_SHORT = 1200

_lock = threading.Lock()


def ph(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:12]


class Store:
    def __init__(self, path: Path):
        self.path = path
        self.f = open(path, "a", encoding="utf-8")
        self.done = set()
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                self.done.add((r["phase"], r["arm"], r["topic"], r["rep"], r["unit"]))
        self.lock = threading.Lock()

    def has(self, key) -> bool:
        return key in self.done

    def write(self, rec: dict):
        with self.lock:
            self.f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            self.f.flush()
            os.fsync(self.f.fileno())
            self.done.add((rec["phase"], rec["arm"], rec["topic"], rec["rep"], rec["unit"]))


def call_and_store(store: Store, phase, arm, topic, rep, unit, messages, **kw):
    key = (phase, arm, topic, rep, unit)
    if store.has(key):
        return None
    rec = client.chat(messages, **kw)
    store.write({
        "phase": phase, "arm": arm, "topic": topic, "rep": rep, "unit": unit,
        "ok": rec["ok"], "text": rec["text"], "finish_reason": rec["finish_reason"],
        "truncated": rec["truncated"], "failure_kind": rec.get("failure_kind"),
        "error": rec.get("error"), "usage": rec.get("usage", {}), "latency": rec.get("latency"),
        "model": rec.get("model"), "at": time.time(),
    })
    return rec


def jsoncall_and_store(store: Store, phase, arm, topic, rep, unit, messages, **kw):
    key = (phase, arm, topic, rep, unit)
    if store.has(key):
        return None
    rec = client.json_call(messages, **kw)
    store.write({
        "phase": phase, "arm": arm, "topic": topic, "rep": rep, "unit": unit,
        "ok": rec["ok"], "text": rec["text"], "parsed": rec.get("parsed"),
        "parse_error": rec.get("parse_error"), "finish_reason": rec["finish_reason"],
        "truncated": rec["truncated"], "failure_kind": rec.get("failure_kind"),
        "error": rec.get("error"), "usage": rec.get("usage", {}), "latency": rec.get("latency"),
        "model": rec.get("model"), "at": time.time(),
    })
    return rec


def build_plan(topics, arms_on, reps, max_branches=4):
    """先声明「应有多少」——收尾要拿它核对实际产出。"""
    plan = {"MAP": [], "GEN": [], "AUD": [], "SKL": []}
    for t in topics:
        for rep in range(reps):
            tid, tp = t["id"], t["prompt"]
            if "A0" in arms_on:
                plan["GEN"].append(("A0", tid, rep, "u0"))
            if "A1" in arms_on:
                for r in arms.ROLES:
                    plan["GEN"].append(("A1", tid, rep, r["id"]))
            if "A2" in arms_on:
                plan["GEN"].append(("A2", tid, rep, "u0"))
            if "A3" in arms_on:
                plan["MAP"].append(("A3", tid, rep, "map"))
                for i in range(4):
                    plan["GEN"].append(("A3", tid, rep, f"b{i}"))
            if "A3c" in arms_on:
                for a in t["axes"]:
                    plan["GEN"].append(("A3c", tid, rep, a["id"]))
            if "A4" in arms_on:
                for g in range(4):
                    plan["GEN"].append(("A4", tid, rep, f"G{g+1}"))
    return plan


def select_branches(parsed, max_branches=4):
    """从地图里取分支：优先每个决策点各取一支（轮转），保证分叉点多样而非同一分叉点堆满。"""
    if not isinstance(parsed, dict):
        return []
    forks = parsed.get("forks") or []
    buckets = []
    for f in forks:
        br = (f or {}).get("branches") or []
        clean = []
        for b in br:
            if not isinstance(b, dict):
                continue
            label = (b.get("label") or "").strip() or "(未命名路线)"
            brief = (b.get("brief") or "").strip() or label
            sig = [s for s in (b.get("signature") or []) if isinstance(s, str) and s.strip()]
            clean.append({"label": label, "brief": brief, "signature": sig[:2]})
        if clean:
            buckets.append(clean)
    picked, i = [], 0
    while len(picked) < max_branches and buckets:
        progressed = False
        for b in list(buckets):
            if len(picked) >= max_branches:
                break
            if i < len(b):
                picked.append(b[i])
                progressed = True
        if not progressed:
            break
        i += 1
    return picked


def run_phase(store, phase, jobs, fn, workers):
    t0 = time.time()
    done_n = 0
    lock = threading.Lock()

    def work(job):
        nonlocal done_n
        try:
            fn(job)
        except Exception as e:  # noqa: BLE001
            print(f"[{phase}] job {job} raised {type(e).__name__}: {e}", flush=True)
        with lock:
            done_n += 1
            if done_n % 20 == 0:
                print(f"  [{phase}] {done_n}/{len(jobs)}  {time.time()-t0:.0f}s", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(work, jobs))
    print(f"[{phase}] done {done_n}/{len(jobs)} in {time.time()-t0:.0f}s", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(RUNS / "run1"))
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--workers", type=int, default=14)
    ap.add_argument("--arms", default="A0,A1,A2,A3,A3c,A4")
    ap.add_argument("--topics", default="")
    ap.add_argument("--gen-max-tokens", type=int, default=MAXTOK_GEN)
    ap.add_argument("--workers-judge", type=int, default=6)
    ap.add_argument("--refudge", action="store_true", help="作废并重判全部 AUD/SKL 记录（判官设置变更时必须用）")
    ap.add_argument("--retry-failed", action="store_true", help="只重跑失败（ok=False）的 AUD/SKL 记录，设置不变")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.refudge and (out / "calls.jsonl").exists():
        # 判官设置变了 ⇒ 旧判官记录整体作废（不能只补失败的：同一把尺子必须用同一套设置）
        keep = []
        dropped = 0
        for line in (out / "calls.jsonl").read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("phase") in ("AUD", "SKL", "SKL2"):
                dropped += 1
                continue
            keep.append(line)
        (out / "calls.jsonl").write_text("\n".join(keep) + ("\n" if keep else ""), encoding="utf-8")
        for junk in ("judge_health.jsonl", "judge_health.json"):
            if (out / junk).exists():
                (out / junk).unlink()
        print(f"refudge: 作废判官记录 {dropped} 条", flush=True)
    if args.retry_failed and (out / "calls.jsonl").exists():
        keep, dropped = [], 0
        for line in (out / "calls.jsonl").read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("phase") in ("AUD", "SKL", "SKL2") and not r.get("ok"):
                dropped += 1
                continue
            keep.append(line)
        (out / "calls.jsonl").write_text("\n".join(keep) + ("\n" if keep else ""), encoding="utf-8")
        print(f"retry-failed: 丢弃失败判官记录 {dropped} 条（设置不变，仅补跑）", flush=True)
    store = Store(out / "calls.jsonl")
    arms_on = set(x for x in args.arms.split(",") if x)
    topics = load_topics()
    if args.topics:
        keep = set(args.topics.split(","))
        topics = [t for t in topics if t["id"] in keep]
    tmap = {t["id"]: t for t in topics}

    plan = build_plan(topics, arms_on, args.reps)
    (out / "manifest.json").write_text(json.dumps({
        "arms": sorted(arms_on), "reps": args.reps,
        "topics": [t["id"] for t in topics],
        "model_gen": MODEL_GEN, "model_judge": MODEL_JUDGE,
        "expected": {k: len(v) for k, v in plan.items()},
        "created": time.time(),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print("plan:", {k: len(v) for k, v in plan.items()}, flush=True)

    # ---------- Phase MAP ----------
    if plan["MAP"]:
        def do_map(job):
            arm, tid, rep, unit = job
            t = tmap[tid]
            rec = jsoncall_and_store(store, "MAP", arm, tid, rep, unit,
                                     [{"role": "user", "content": arms.p_map(t)}],
                                     model=MODEL_GEN, temperature=TEMP_MAP, max_tokens=MAXTOK_JSON)
            # 升级重试：思考 token 吃光预算 ⇒ 截断 ⇒ 显式升级预算再试一次
            if rec is not None and not rec.get("ok"):
                store.done.discard(("MAP", arm, tid, rep, unit))
                jsoncall_and_store(store, "MAP", arm, tid, rep, unit,
                                   [{"role": "user", "content": arms.p_map(t)}],
                                   model=MODEL_GEN, temperature=TEMP_MAP, max_tokens=MAXTOK_JSON * 2)
        run_phase(store, "MAP", plan["MAP"], do_map, args.workers)

    # 读回 MAP 结果
    maps = {}
    if (out / "calls.jsonl").exists():
        for line in (out / "calls.jsonl").read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r["phase"] == "MAP":
                maps[(r["arm"], r["topic"], r["rep"])] = r.get("parsed")

    # ---------- Phase GEN ----------
    gen_jobs = []
    for arm, tid, rep, unit in plan["GEN"]:
        gen_jobs.append((arm, tid, rep, unit))
    briefs = {}  # (arm,tid,rep,unit) -> brief（供审计用）

    def do_gen(job):
        arm, tid, rep, unit = job
        t = tmap[tid]
        if arm == "A0":
            msg = [{"role": "user", "content": arms.p_base(t)}]
            brief = None
        elif arm == "A1":
            role = next(r for r in arms.ROLES if r["id"] == unit)
            msg = [{"role": "user", "content": arms.p_persona(t, role)}]
            brief = role["desc"]
        elif arm == "A2":
            msg = [{"role": "user", "content": arms.p_onemulti(t)}]
            brief = None
        elif arm == "A3":
            parsed = maps.get((arm, tid, rep))
            branches = select_branches(parsed, 4)
            if not branches:
                # 地图不可用 ⇒ 显式记失败，不静默退回基线
                store.write({"phase": "GEN", "arm": arm, "topic": tid, "rep": rep, "unit": unit,
                             "ok": False, "text": "", "parsed": None, "parse_error": "no_branches",
                             "finish_reason": None, "truncated": False, "failure_kind": "map_unusable",
                             "error": None, "usage": {}, "latency": 0, "model": MODEL_GEN, "at": time.time()})
                return
            idx = int(unit[1:])
            if idx >= len(branches):
                return
            b = branches[idx]
            msg = [{"role": "user", "content": arms.p_branch(t, b["brief"], b["signature"])}]
            brief = b["brief"]
        elif arm == "A3c":
            ax = next(a for a in t["axes"] if a["id"] == unit)
            msg = [{"role": "user", "content": arms.p_branch_curated(t, ax)}]
            brief = ax["feed"]
        elif arm == "A4":
            gi = int(unit[1:]) - 1
            dim = {"G1": GENERIC_DIM(0), "G2": GENERIC_DIM(1), "G3": GENERIC_DIM(2), "G4": GENERIC_DIM(3)}[unit]
            msg = [{"role": "user", "content": arms.p_branch_generic(t, dim)}]
            brief = dim["brief"]
        else:
            return
        rec = call_and_store(store, "GEN", arm, tid, rep, unit, msg,
                             model=MODEL_GEN, temperature=TEMP_GEN, max_tokens=args.gen_max_tokens)
        if rec is not None:
            with _lock:
                briefs[(arm, tid, rep, unit)] = brief

    def GENERIC_DIM(i):
        from arms import GENERIC_DIMENSIONS
        return GENERIC_DIMENSIONS[i]

    run_phase(store, "GEN", gen_jobs, do_gen, args.workers)

    # 收集所有产出 + brief
    outputs = []  # (arm,tid,rep,unit,text,brief)
    for line in (out / "calls.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r["phase"] == "GEN":
            outputs.append(r)

    # 从 prompt 反推 brief（AUD 阶段用）
    def brief_for(r):
        arm, tid, unit = r["arm"], r["topic"], r["unit"]
        t = tmap[tid]
        if arm == "A1":
            role = next(x for x in arms.ROLES if x["id"] == unit)
            return role["desc"]
        if arm == "A3":
            parsed = maps.get((arm, tid, r["rep"]))
            bs = select_branches(parsed, 4)
            idx = int(unit[1:])
            return bs[idx]["brief"] if idx < len(bs) else None
        if arm == "A3c":
            ax = next(a for a in t["axes"] if a["id"] == unit)
            return ax["feed"]
        if arm == "A4":
            from arms import GENERIC_DIMENSIONS
            return GENERIC_DIMENSIONS[int(unit[1:]) - 1]["brief"]
        return None

    # ---------- Phase AUD ----------
    aud_jobs = []
    for r in outputs:
        if r["arm"] in ("A1", "A3", "A3c", "A4") and r.get("ok"):
            aud_jobs.append((r["arm"], r["topic"], r["rep"], r["unit"]))

    def do_aud(job):
        arm, tid, rep, unit = job
        t = tmap[tid]
        r = next(x for x in outputs if x["arm"] == arm and x["topic"] == tid and x["rep"] == rep and x["unit"] == unit)
        b = brief_for(r)
        if not b:
            return
        jsoncall_and_store(store, "AUD", arm, tid, rep, unit,
                           [{"role": "user", "content": arms.p_audit(t, b, r["text"])}],
                           model=MODEL_JUDGE, temperature=0.0, max_tokens=MAXTOK_SHORT,
                           retries=4, thinking="disabled")

    run_phase(store, "AUD", aud_jobs, do_aud, args.workers_judge)

    # ---------- Phase SKL ----------
    skl_jobs = [(r["arm"], r["topic"], r["rep"], r["unit"]) for r in outputs if r.get("ok")]

    def do_skl(job):
        arm, tid, rep, unit = job
        t = tmap[tid]
        r = next(x for x in outputs if x["arm"] == arm and x["topic"] == tid and x["rep"] == rep and x["unit"] == unit)
        jsoncall_and_store(store, "SKL", arm, tid, rep, unit,
                           [{"role": "user", "content": arms.p_skeleton(t, r["text"])}],
                           model=MODEL_JUDGE, temperature=0.0, max_tokens=MAXTOK_SHORT,
                           retries=4, thinking="disabled")

    run_phase(store, "SKL", skl_jobs, do_skl, args.workers_judge)

    # ---------- 收尾核对 ----------
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    counts = {k: 0 for k in plan}
    gen_ok = 0
    aud_brief_ok = 0
    for line in (out / "calls.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r["phase"] in counts:
            counts[r["phase"]] += 1
        if r["phase"] == "GEN":
            if r.get("ok"):
                gen_ok += 1
                if r["arm"] in ("A1", "A3", "A3c", "A4"):
                    aud_brief_ok += 1
    # 期望值：MAP/GEN 由计划决定；AUD/SKL 由「产出里有多少条可审」决定
    expected = dict(manifest["expected"])
    expected["AUD"] = aud_brief_ok
    expected["SKL"] = gen_ok
    actual = {k: counts.get(k, 0) for k in expected}
    print("expected:", expected)
    print("actual  :", actual)
    missing = {k: (expected[k], actual[k]) for k in expected if actual[k] != expected[k]}
    (out / "integrity.json").write_text(json.dumps(
        {"expected": expected, "actual": actual, "mismatch": missing}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    if missing:
        print(f"!! 数量不符（不静默归零，请显式处理）: {missing}", file=sys.stderr)
    print("run finished ->", out)


if __name__ == "__main__":
    main()
