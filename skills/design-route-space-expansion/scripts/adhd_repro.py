"""开源 ADHD 项目（UditAkhourii/adhd）的**机制复现**。

⚠️ **必须如实声明**：这不是原项目本体，是**同算法的 Python 复刻**。
- 原项目走 claude-agent-sdk（Claude Code CLI 作子进程），该通道在实验当天挂死
  （内部报 `Claude Code process exited with code 1`，连简单问题都零输出，1200s 超时）。
- 因此照着 `src/engine.ts` / `src/frames.ts` / `src/render.ts` 逐行复刻算法，
  只把**传输层**换成可用的 API 通道。
- 差异（必须写进报告）：
  1. 原用 `systemPrompt: {preset:"claude_code", append: X}`，会叠加 Claude Code 自己的
     系统提示；复刻版只注入项目自己的 system prompt。
  2. 帧选择是 Fisher-Yates 随机抽；复刻版同样随机（同分布）。
  3. 5 帧 × 6 想法、deepen top3、并发 4 —— 全部照搬。

**为什么值得复现而不是砍掉这个臂**：用户明确要求跑「开源 ADHD 项目」。
砍掉 = 少一个最重要的外部对照。用复刻版 + 明确标注，比留空诚实得多。
"""
from __future__ import annotations
import json
import os
import random
import re
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from creativity_lab.client import LLM   # noqa: E402

# ---------------------------------------------------------------- 帧（src/packs/core.ts 原样搬）
FRAMES = [
    ("hardware-eyes", "Hardware engineer",
     "You think in latency, memory layout, and physical constraints. Re-ask this problem as if it were a hardware/firmware problem. What does the bus topology, the cache, the timing budget tell you?",
     ["code", "wild"]),
    ("regulator", "Regulator / auditor",
     "You audit systems for compliance and failure modes. What ideas surface when you ask: what must be provable, traceable, or refusable here?",
     ["design", "general"]),
    ("ten-year-old", "10-year-old",
     "You are a curious 10-year-old who has never seen software before. Describe naive but unencumbered approaches. Ignore convention.",
     ["general", "wild"]),
    ("adversary", "Competitor trying to break it",
     "You are a hostile competitor or attacker. Generate approaches that exploit, fail, or sabotage the obvious solution. Then invert into ideas.",
     ["code", "design"]),
    ("biology", "Cross-domain: biology",
     "Transplant a mechanism from biology — immune systems, neural plasticity, cell signaling, evolution, gut flora — and force-fit it onto this engineering problem.",
     ["code", "wild"]),
    ("logistics", "Cross-domain: logistics / supply chain",
     "Steal mechanisms from logistics: queues, batching, just-in-time, hub-and-spoke, returns, last-mile. Apply them literally to this problem.",
     ["code", "design"]),
    ("game-design", "Cross-domain: game design",
     "Approach this as a game designer. What are the loops, rewards, friction, save-states, speedrun tricks? Treat the user/system as a player.",
     ["design", "general"]),
    ("markets", "Cross-domain: markets",
     "Treat the problem as a market. Who are the buyers, sellers, market-makers? What does an auction, a futures contract, a clearing house look like here?",
     ["design", "wild"]),
    ("inversion", "Inversion",
     "Ask the OPPOSITE question. If the goal is X, brainstorm 'how would we guarantee NOT-X' — then negate each answer back into an idea.",
     ["code", "design", "general"]),
    ("extreme-zero", "Extreme: $0 budget, 1 hour",
     "You have no money, no team, one hour. What's the crudest version that still does the load-bearing thing? Hacks, hardcoded values, manual loops welcome.",
     ["code", "general"]),
    ("extreme-infinite", "Extreme: infinite budget, 10 years",
     "You have infinite compute, infinite engineers, a decade. What does the maximalist version look like? What would only be possible at that scale?",
     ["design", "wild"]),
    ("remove-assumption", "Remove the load-bearing assumption",
     "Name the thing everyone treats as fixed in this problem (the framework, the database, the request/response model, the file system, the network). Imagine it's gone. Generate ideas that only exist in that world.",
     ["code", "design", "wild"]),
    ("speedrunner", "Speedrunner",
     "You're a speedrunner. Find glitches, skips, out-of-bounds tricks, frame-perfect shortcuts. What's the abusive-but-legal path through this problem?",
     ["code", "wild"]),
    ("ant-colony", "Ant colony / swarm",
     "No central planner. Many dumb agents, local rules, pheromone trails. How does the problem solve itself emergently?",
     ["code", "wild"]),
    ("ops-3am", "On-call at 3am",
     "You're the on-call engineer woken at 3am when this thing breaks. What design would let you not get paged? What's the runbook-shaped solution?",
     ["code", "design"]),
]

DIVERGE_SYSTEM = """You are in DIVERGENT mode. You are a generator, not a critic.
Rules:
- Output a JSON array only. No prose before/after.
- Generate the requested number of distinct ideas.
- Each idea is a SHORT phrase or single sentence. No paragraphs.
- Push past the obvious. The first 3 ideas you'd think of are banned —
  assume the reader already had those. Aim for the awkward middle.
- Bad, weird, and absurd ideas are welcome; they seed better ones.
- Do not evaluate, hedge, or rank. Just generate."""

SCORE_SYSTEM = """You are in CONVERGENT mode. You are now the critic.
Score each idea on three axes 0-10:
- novelty: distance from the obvious default solution
- viability: could this actually ship / work in practice
- fit: how directly it addresses the stated problem

Tell the truth about weaknesses — don't soften the substance. But the
critic's job is to produce two symmetric signals, not just one:

- "strength": required for every idea, even weak ones. The single most
  concrete thing this idea gets right that a competing idea doesn't.
- "trap" (optional): if the idea looks attractive but has a hidden cost
  (false economy, won't scale, premature abstraction), name it as a
  specific, actionable heads-up — e.g. "solid for a prototype, breaks
  past 10k concurrent users" — not a dismissal like "bad idea." The
  fact stays the fact; only the framing changes: information you can
  act on, not a verdict on the idea's worth.

Output JSON only."""

CLUSTER_SYSTEM = """You group ideas into 3-6 clusters by their UNDERLYING ANGLE
(not by surface keywords). Cluster labels name the angle, e.g.
"remove-the-server plays", "push-work-to-client plays", "cache-shaped plays".
Output JSON only."""

REFRAME_SYSTEM = """You strip load-bearing anchors from a problem statement before divergent
brainstorming. An anchor is an incidental implementation detail (a specific
tech stack, an existing tool name, the current architecture) that isn't a
real constraint but silently narrows every downstream idea to variations on
what's already there.

Rules:
- Keep anchors that are genuine immutable constraints: compliance/legal
  requirements, hard budget or time limits, physical/protocol constraints,
  anything the user would reject an answer for violating.
- Strip anchors that are just "how it happens to be built today" — current
  database, current framework, current team structure — UNLESS removing
  them would make the problem meaningless or invite disallowed options.
- If you strip something, restate the problem as the underlying
  job-to-be-done, not the current implementation.
- If nothing needs stripping, return the problem unchanged and set
  "changed" to false.
Output JSON only: {"reframed": "...", "changed": true|false, "note": "one clause on what was stripped, omit if unchanged"}"""

DEEPEN_SYSTEM = """You are in FOCUS mode. Take one promising idea and connect dots:
- Sketch how it would actually work (4-8 sentences).
- Name the load-bearing risk.
- Name the first concrete step a coder would take.
- Then generate 3-5 sub-ideas that branch off this one (variations,
  combinations with other domains, things this unlocks).
Output JSON only."""


def parse_json(raw: str):
    """照搬 src/llm.ts parseJSON：剥围栏 + 取第一个 { 或 [。"""
    t = (raw or "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if fence:
        t = fence.group(1).strip()
    i = t.find("{")
    j = t.find("[")
    starts = [x for x in (i, j) if x >= 0]
    if not starts:
        raise ValueError("no JSON")
    s = min(starts)
    end = (t.rfind("]") + 1) if (j >= 0 and (i < 0 or j < i)) else (t.rfind("}") + 1)
    if end <= 0:
        raise ValueError("unterminated JSON")
    return json.loads(t[s:end])


def select_frames(n=5, code_mode=True, rng=None):
    """照搬 src/frames.ts selectFrames：Fisher-Yates 洗牌 + 必含一个 wild 帧。"""
    rng = rng or random
    frames = list(FRAMES)
    if code_mode:
        eng = [f for f in frames if ("code" in f[3] or "design" in f[3])]
        pool = eng if eng else frames
    else:
        pool = frames
    wilds = [f for f in frames if "wild" in f[3]] or [f for f in FRAMES if "wild" in f[3]]
    a = list(pool)
    for i in range(len(a) - 1, 0, -1):
        k = rng.randrange(i + 1)
        a[i], a[k] = a[k], a[i]
    picked = a[:max(1, n - 1)]
    wp = wilds[rng.randrange(len(wilds))]
    if not any(f[0] == wp[0] for f in picked):
        picked.append(wp)
    return picked[:n]


def run_adhd(problem, model="", llm=None, frames_n=5, ideas_per_frame=6, top_k=3,
             concurrency=4, seed=None):
    """复刻 engine.ts 的 run()。返回 (rendered_text, meta)。"""
    llm = llm or LLM()
    rng = random.Random(seed)
    frames = select_frames(frames_n, True, rng)
    meta = dict(frames=[f[1] for f in frames], n_calls=0, failed=[])

    # ---- PHASE 0 REFRAME ----
    div_problem = problem
    raw = llm.chat("PROBLEM:\n%s\n\nStrip incidental anchors, keep real constraints. "
                   "Output JSON only." % problem, model=model, purpose="adhd_reframe",
                   max_tokens=2000, budgets=(3000,), min_ok=10) or ""
    meta["n_calls"] += 1
    try:
        r = parse_json(raw)
        if r.get("changed") and str(r.get("reframed", "")).strip():
            div_problem = r["reframed"]
    except Exception:
        pass                                   # fail open（与原实现一致）

    # ---- PHASE 1 DIVERGE（纯并行，分支互不可见）----
    def _branch(f):
        fid, label, prompt, _tags = f
        user = ("PROBLEM:\n%s\n\nFRAME — %s:\n%s\n\nGenerate %d ideas under this frame.\n"
                "Output JSON array: [{\"text\": \"...\", \"rationale\": \"...\"}]\n"
                "- text: one phrase/sentence, the idea itself\n"
                "- rationale: 1 short clause on why this frame surfaces it (optional)"
                % (div_problem, label, prompt, ideas_per_frame))
        raw = llm.chat(user, model=model, purpose="adhd_diverge", max_tokens=2000,
                       budgets=(3000, 4000), min_ok=10) or ""
        try:
            rows = parse_json(raw)
            ideas = [str(x.get("text", "")).strip() for x in rows
                     if isinstance(x, dict) and str(x.get("text", "")).strip()]
        except Exception:
            ideas = []
        return fid, label, ideas

    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        res = list(ex.map(_branch, frames))
    meta["n_calls"] += len(frames)
    branches = [(fid, label, ideas) for fid, label, ideas in res if ideas]
    for fid, label, ideas in res:
        if not ideas:
            meta["failed"].append(fid)
    if not branches:
        return "", meta

    all_ideas = []
    for i, (fid, label, ideas) in enumerate(branches):
        for j, t in enumerate(ideas):
            all_ideas.append(dict(id="i%d_%d" % (i, j), frameId=fid, text=t))

    # ---- PHASE 2 SCORE + CLUSTER（并行，判官回归）----
    ideas_block = "\n".join("%s :: %s" % (x["id"], x["text"]) for x in all_ideas)

    def _score():
        return _chat_json(llm, SCORE_SYSTEM,
                          "PROBLEM:\n%s\n\nIDEAS (id → text):\n%s\n\nScore each. Output JSON array:\n"
                          "[{\"id\":\"...\",\"novelty\":0-10,\"viability\":0-10,\"fit\":0-10,"
                          "\"strength\":\"...\",\"trap\":\"... or omit\"}]" % (problem, ideas_block),
                          model, "adhd_score")

    def _cluster():
        return _chat_json(llm, CLUSTER_SYSTEM,
                          "PROBLEM:\n%s\n\nIDEAS:\n%s\n\nOutput JSON: "
                          "[{\"label\":\"...\",\"ideaIds\":[\"...\",\"...\"]}]" % (problem, ideas_block),
                          model, "adhd_cluster")

    with ThreadPoolExecutor(max_workers=2) as ex:
        f_score, f_cluster = ex.submit(_score), ex.submit(_cluster)
        score_rows, cluster_rows = f_score.result(), f_cluster.result()
    meta["n_calls"] += 2

    smap = {}
    for r in (score_rows or []):
        if not isinstance(r, dict):
            continue
        try:
            nv, vi, ft = float(r.get("novelty", 0)), float(r.get("viability", 0)), float(r.get("fit", 0))
        except Exception:
            continue
        smap[r.get("id")] = dict(novelty=nv, viability=vi, fit=ft,
                                 total=nv * 0.35 + vi * 0.4 + ft * 0.25,
                                 trap=r.get("trap"), strength=r.get("strength"))
    cl = {}
    for c in (cluster_rows or []):
        if isinstance(c, dict) and c.get("label"):
            for i in (c.get("ideaIds") or []):
                cl[i] = c["label"]
    for x in all_ideas:
        x["score"] = smap.get(x["id"])
        x["cluster"] = cl.get(x["id"])

    traps = [x for x in all_ideas if x["score"] and x["score"].get("trap")]
    ranked = sorted([x for x in all_ideas if x["score"] and not x["score"].get("trap")],
                    key=lambda x: -x["score"]["total"])
    shortlist = ranked[:max(2, min(4, top_k + 1))]
    non_obvious = None
    if shortlist:
        non_obvious = sorted(shortlist, key=lambda x: -(x["score"]["novelty"] + x["score"]["viability"] * 0.5))[0]

    # ---- PHASE 3 DEEPEN top-K ----
    to_deepen = ranked[:top_k]

    def _deepen(idea):
        sib = "\n".join("- %s" % y["text"] for y in all_ideas if y["id"] != idea["id"])[:1200]
        return _chat_json(llm, DEEPEN_SYSTEM,
                          "PROBLEM:\n%s\n\nFOCUS IDEA:\n%s\n\nSIBLING IDEAS (use for recombination if useful):\n%s\n\n"
                          "Output JSON:\n{\"sketch\": \"4-8 sentences. How it works. Load-bearing risk. First concrete step.\","
                          " \"childIdeas\": [{\"text\": \"...\", \"rationale\": \"variation / hybrid / unlock\"}]}"
                          % (problem, idea["text"], sib), model, "adhd_deepen")

    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        deep_rows = list(ex.map(_deepen, to_deepen))
    meta["n_calls"] += len(to_deepen)

    # ---- 渲染（照搬 render.ts 的文本形状）----
    out = ["Problem: " + problem]
    if div_problem != problem:
        out.append("Reframed for divergence: " + div_problem)
    out.append("")
    out.append("Wide set")
    by_cluster = {}
    for x in all_ideas:
        by_cluster.setdefault(x.get("cluster") or "(unclustered)", []).append(x)
    for label, items in by_cluster.items():
        out.append("  " + label)
        for i in items:
            chip = ""
            if i["score"]:
                chip = " [N%s V%s F%s]" % (i["score"]["novelty"], i["score"]["viability"], i["score"]["fit"])
            out.append("    - %s%s" % (i["text"], chip))
    out.append("")
    out.append("Converge — shortlist")
    for i in shortlist:
        mark = "★ non-obvious pick → " if (non_obvious and non_obvious["id"] == i["id"]) else "  "
        chip = ""
        if i["score"]:
            chip = " [N%s V%s F%s]" % (i["score"]["novelty"], i["score"]["viability"], i["score"]["fit"])
        out.append("  %s%s%s" % (mark, i["text"], chip))
    out.append("")
    if traps:
        out.append("Traps (watch-outs, not verdicts)")
        for t in traps:
            out.append("  ⚠ " + t["text"])
            if t["score"].get("trap"):
                out.append("    " + t["score"]["trap"])
        out.append("")
    out.append("Focus — deepened branches")
    for idea, dr in zip(to_deepen, deep_rows):
        out.append("  → " + idea["text"])
        if isinstance(dr, dict):
            out.append("    " + str(dr.get("sketch", "")))
            for c in (dr.get("childIdeas") or []):
                if isinstance(c, dict) and c.get("text"):
                    out.append("      · " + str(c["text"]))
        out.append("")
    out.append("Provocation")
    wild = sorted([x for x in all_ideas if x["score"]], key=lambda x: -x["score"]["novelty"])
    out.append("  What if we took this seriously: %s" %
               (wild[0]["text"] if wild else "What's the assumption nobody named yet?"))
    # ★★ 2026-10-24 最小侵入扩展（不重写任何逻辑）：
    #   外部要测「面宽」必须拿到分支列表 ⇒ 原实现只返回渲染后的合并文本
    #   ⇒ 这里把想法列表也放进 meta（调用方可选用，不影响原调用方）
    meta["ideas"] = [x.get("text", "") for x in all_ideas if x.get("text")]
    meta["ideas_meta"] = [{"id": x.get("id"), "frameId": x.get("frameId"),
                           "text": x.get("text", ""),
                           "score": x.get("score")} for x in all_ideas]
    return "\n".join(out), meta


def _chat_json(llm, system, user, model, purpose):
    raw = llm.chat(user, model=model, purpose=purpose, max_tokens=2000,
                   budgets=(3000, 4000), min_ok=10) or ""
    try:
        return parse_json(raw)
    except Exception:
        return None
