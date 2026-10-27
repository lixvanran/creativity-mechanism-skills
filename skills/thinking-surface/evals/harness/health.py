"""判官健康度：用另一个模型重跑一部分审计，比一致率。

为什么必须做：审计用的是 LLM 判官。判官坏了，读数就是"关于仪器的证据"而不是"关于世界的证据"。
做法：随机抽 10% 的 AUD / SKL 记录，用另一个模型（M3 vs M2.7）重跑，比对结果是否翻转。

口径：
  抽样 = 按 (arm,topic,rep,unit) 随机取 10%（固定随机种子，可复现）
  一致 = AUD 的 hit 布尔相同；SKL 的骨架 Jaccard ≥ 0.5 视为一致
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import arms  # noqa: E402
import client  # noqa: E402
import measure  # noqa: E402
from check_topics import load_topics  # noqa: E402

ALT_MODEL = "MiniMax-M3"
FRAC = 0.10
SEED = 20261026


def main(run_dir: str):
    run = Path(run_dir)
    topics = {t["id"]: t for t in load_topics()}
    recs = [json.loads(l) for l in (run / "calls.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    gen = {(r["arm"], r["topic"], r["rep"], r["unit"]): r for r in recs if r["phase"] == "GEN"}
    aud = {(r["arm"], r["topic"], r["rep"], r["unit"]): r for r in recs if r["phase"] == "AUD"}
    skl = {(r["arm"], r["topic"], r["rep"], r["unit"]): r for r in recs if r["phase"] == "SKL"}
    maps = {(r["arm"], r["topic"], r["rep"]): r.get("parsed") for r in recs if r["phase"] == "MAP"}

    def brief_for(arm, tid, rep, unit):
        t = topics[tid]
        if arm == "A1":
            return next(x for x in arms.ROLES if x["id"] == unit)["desc"]
        if arm == "A3":
            from run import select_branches
            bs = select_branches(maps.get((arm, tid, rep)), 4)
            i = int(unit[1:])
            return bs[i]["brief"] if i < len(bs) else None
        if arm == "A3c":
            return next(a for a in t["axes"] if a["id"] == unit)["feed"]
        if arm == "A4":
            return arms.GENERIC_DIMENSIONS[int(unit[1:]) - 1]["brief"]
        return None

    rnd = random.Random(SEED)
    aud_keys = sorted(aud.keys())
    skl_keys = sorted(skl.keys())
    aud_sample = [k for k in aud_keys if rnd.random() < FRAC]
    skl_sample = [k for k in skl_keys if rnd.random() < FRAC]

    from concurrent.futures import ThreadPoolExecutor
    import threading
    lock = threading.Lock()
    out = {"aud_agree": [], "skl_agree": [], "n_aud": 0, "n_skl": 0}
    f = open(run / "judge_health.jsonl", "a", encoding="utf-8")

    def do_aud(k):
        arm, tid, rep, unit = k
        g = gen.get(k)
        if not g:
            return
        b = brief_for(arm, tid, rep, unit)
        if not b:
            return
        t = topics[tid]
        rec = client.json_call([{"role": "user", "content": arms.p_audit(t, b, g["text"])}],
                               model=ALT_MODEL, temperature=0.0, max_tokens=1200,
                               retries=4, thinking="disabled")
        orig = aud[k].get("parsed") or {}
        new = rec.get("parsed") or {}
        ok = (isinstance(orig, dict) and isinstance(new, dict)
              and "hit" in orig and "hit" in new and bool(orig["hit"]) == bool(new["hit"]))
        with lock:
            out["aud_agree"].append(ok)
            out["n_aud"] += 1
            f.write(json.dumps({"phase": "HEALTH_AUD", "arm": arm, "topic": tid, "rep": rep, "unit": unit,
                                 "orig": orig, "new": new, "agree": ok,
                                 "orig_model": aud[k].get("model"), "new_model": ALT_MODEL,
                                 "new_ok": rec["ok"]}, ensure_ascii=False) + "\n")

    def do_skl(k):
        arm, tid, rep, unit = k
        g = gen.get(k)
        if not g:
            return
        t = topics[tid]
        rec = client.json_call([{"role": "user", "content": arms.p_skeleton(t, g["text"])}],
                               model=ALT_MODEL, temperature=0.0, max_tokens=1200,
                               retries=4, thinking="disabled")
        o = (skl[k].get("parsed") or {}).get("skeleton") or []
        n = (rec.get("parsed") or {}).get("skeleton") or []
        j = measure.jaccard(set(o), set(n))
        with lock:
            out["skl_agree"].append(j)
            out["n_skl"] += 1
            f.write(json.dumps({"phase": "HEALTH_SKL", "arm": arm, "topic": tid, "rep": rep, "unit": unit,
                                 "jaccard": j, "orig": o, "new": n,
                                 "orig_model": skl[k].get("model"), "new_model": ALT_MODEL,
                                 "new_ok": rec["ok"]}, ensure_ascii=False) + "\n")

    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(do_aud, aud_sample))
        list(ex.map(do_skl, skl_sample))
    f.close()

    a = out["aud_agree"]
    s = out["skl_agree"]
    summary = {
        "alt_model": ALT_MODEL,
        "frac": FRAC, "seed": SEED,
        "aud_n": len(a), "aud_agree": sum(1 for x in a if x),
        "aud_agree_rate": (sum(1 for x in a if x) / len(a)) if a else None,
        "skl_n": len(s), "skl_mean_jaccard": (sum(s) / len(s)) if s else None,
        "skl_agree_rate_ge_0.5": (sum(1 for x in s if x >= 0.5) / len(s)) if s else None,
    }
    (run / "judge_health.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "runs/main1")
