"""A2 逐条思路的骨架抽取（补齐可比性）。

A2 一次调用输出 4 条思路，SKL 阶段只对整段抽了一次骨架 ⇒ 拿不到 4 条思路各自的机制骨架。
本脚本把 A2 的输出按语义小标题切成思路后逐条抽骨架，写回同一 calls.jsonl（phase=SKL2）。

不重跑已有记录，幂等。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import arms  # noqa: E402
import client  # noqa: E402
import measure  # noqa: E402
from check_topics import load_topics  # noqa: E402

MODEL = "MiniMax-M2.7"


def main(run_dir: str):
    run = Path(run_dir)
    topics = {t["id"]: t for t in load_topics()}
    recs = [json.loads(l) for l in (run / "calls.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    done = set()
    for r in recs:
        if r["phase"] == "SKL2":
            done.add((r["arm"], r["topic"], r["rep"], r["unit"]))

    jobs = []
    for r in recs:
        if r["phase"] == "GEN" and r["arm"] == "A2" and r.get("ok"):
            ideas, note = measure.split_ideas(r["text"], strict=True)
            if note != "split":
                continue
            for i, idea in enumerate(ideas):
                key = (r["arm"], r["topic"], r["rep"], f"{r['unit']}#{i}")
                if key not in done:
                    jobs.append((r, i, idea))
    print(f"A2 待抽骨架 {len(jobs)} 条")

    from concurrent.futures import ThreadPoolExecutor
    import threading
    lock = threading.Lock()
    f = open(run / "calls.jsonl", "a", encoding="utf-8")

    def work(job):
        r, i, idea = job
        t = topics[r["topic"]]
        rec = client.json_call([{"role": "user", "content": arms.p_skeleton(t, idea)}],
                               model=MODEL, temperature=0.0, max_tokens=1200,
                               retries=4, thinking="disabled")
        out = {
            "phase": "SKL2", "arm": r["arm"], "topic": r["topic"], "rep": r["rep"],
            "unit": f"{r['unit']}#{i}", "ok": rec["ok"], "text": rec["text"], "parsed": rec.get("parsed"),
            "parse_error": rec.get("parse_error"), "finish_reason": rec["finish_reason"],
            "truncated": rec["truncated"], "failure_kind": rec.get("failure_kind"),
            "error": rec.get("error"), "usage": rec.get("usage", {}), "latency": rec.get("latency"),
            "model": rec.get("model"),
        }
        with lock:
            f.write(json.dumps(out, ensure_ascii=False) + "\n")
            f.flush()

    with ThreadPoolExecutor(max_workers=12) as ex:
        list(ex.map(work, jobs))
    f.close()
    print("done ->", run / "calls.jsonl")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "runs/main1")
