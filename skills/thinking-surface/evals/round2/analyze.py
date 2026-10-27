"""分析器：从 calls.jsonl 出读数表 + 执行预注册的判决线。

判决线（prereg.md §5，公式型，事前定死）：
  X 优于 Y ⟺ ①各题均值差 > 0  ②≥2/3 题同向  ③≥2/3 题上差值 > max(sd_X, sd_Y)
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import measure  # noqa: E402
from check_topics import load_topics  # noqa: E402

ARMS = ["A0", "A1", "A2", "A3", "A3c", "A4"]
ARMS_CN = {
    "A0": "基线（1次）",
    "A1": "身份臂（4人设）",
    "A2": "单提示多视角（1次出4条）",
    "A3": "路径合约 TSC（自测绘）",
    "A3c": "路径合约（外部给定轴）",
    "A4": "H0 臂（任务无关维度）",
    "A4b": "同轴库裸给（H0-12）",
    "A5": "★ skill 完整规程",
}


def load(run_dir: Path):
    recs = []
    for line in (run_dir / "calls.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            recs.append(json.loads(line))
        except Exception:
            pass
    return recs


def build_units(recs, topics_by_id):
    """(arm, topic, rep) -> {units: [...], unit_meta: [...]}"""
    gen = {}
    for r in recs:
        if r["phase"] == "GEN":
            gen.setdefault((r["arm"], r["topic"], r["rep"]), []).append(r)

    aud = {}
    for r in recs:
        if r["phase"] == "AUD":
            aud[(r["arm"], r["topic"], r["rep"], r["unit"])] = r

    skl = {}
    for r in recs:
        if r["phase"] == "SKL":
            skl[(r["arm"], r["topic"], r["rep"], r["unit"])] = r
    skl2 = {}
    for r in recs:
        if r["phase"] == "SKL2":
            skl2[(r["arm"], r["topic"], r["rep"], r["unit"])] = r

    out = {}
    for (arm, tid, rep), rs in gen.items():
        rs = sorted(rs, key=lambda r: r["unit"])
        units, meta = [], []
        for r in rs:
            if not r.get("ok"):
                continue
            txt = r["text"]
            if arm == "A2":
                ideas, note = measure.split_ideas(txt, strict=True)
                if note == "split":
                    for i, idea in enumerate(ideas):
                        units.append(idea)
                        meta.append({"unit": f"{r['unit']}#{i}", "skel_key": f"{r['unit']}#{i}", "src": r["unit"]})
                else:
                    units.append(txt)
                    meta.append({"unit": r["unit"], "skel_key": r["unit"], "src": r["unit"], "split_note": note})
            else:
                units.append(txt)
                meta.append({"unit": r["unit"], "skel_key": r["unit"], "src": r["unit"]})
        out[(arm, tid, rep)] = {"units": units, "meta": meta}
    return out, aud, skl, skl2


def unit_skeleton(arm, tid, rep, unit_meta, skl, skl2):
    """取一条思路的骨架：A2 的思路用 SKL2（逐条抽取），其余用 SKL。"""
    key = (arm, tid, rep, unit_meta["skel_key"])
    if arm == "A2" and key in skl2:
        r = skl2[key]
    elif key in skl:
        r = skl[key]
    else:
        return None
    p = r.get("parsed")
    if not isinstance(p, dict):
        return None
    return {
        "skeleton": p.get("skeleton") or [],
        "vague": p.get("vague"),
        "actionable": p.get("actionable"),
        "on_topic": p.get("on_topic"),
    }


def per_rep_metrics(arm, tid, rep, pack, aud, skl, skl2, topics_by_id):
    t = topics_by_id[tid]
    units = pack["units"]
    meta = pack["meta"]
    if not units:
        return None
    axes = t.get("axes", [])

    cov = measure.coverage_union(axes, units)
    units250 = [u[:250] for u in units]
    cov250 = measure.coverage_union(axes, units250)
    # 同 n 配平：跨臂比较必须给每臂同样的"机会数"（各臂思路条数不同：
    # A0=1, A1/A3/A4=4, A3c=5 ⇒ 并集覆盖天然随条数涨）
    u3 = units[:3]
    cov3 = measure.coverage_union(axes, u3)
    # 每条思路的平均覆盖（"聚焦度"：一条思路同时踩了几条轴）
    per_unit = []
    for u in units:
        per_unit.append(measure.coverage_union(axes, [u])["n_covered"])
    cov_per_unit = sum(per_unit) / len(per_unit) if per_unit else None

    skels = []
    vague, action, on_topic = [], [], []
    for m in meta:
        s = unit_skeleton(arm, tid, rep, m, skl, skl2)
        if s:
            skels.append(s["skeleton"])
            if s["vague"] is not None:
                vague.append(bool(s["vague"]))
            if isinstance(s["actionable"], (int, float)):
                action.append(float(s["actionable"]))
            if s["on_topic"] is not None:
                on_topic.append(bool(s["on_topic"]))

    hits = []
    for m in meta:
        r = aud.get((arm, tid, rep, m["src"]))
        if r is not None and isinstance(r.get("parsed"), dict) and "hit" in r["parsed"]:
            hits.append(bool(r["parsed"]["hit"]))

    skel_dist = measure.skeleton_distance(skels)
    cos_dist = mean_pairwise_cos(units)
    neg = sum(measure.neg_marker_rate(u) for u in units) / len(units)
    chars = sum(len(u) for u in units)
    tok_p = sum((r.get("usage") or {}).get("prompt_tokens", 0) or 0 for r in [])
    return {
        "arm": arm, "topic": tid, "rep": rep,
        "n_units": len(units),
        "cov": cov["n_covered"],
        "cov250": cov250["n_covered"],
        "cov3": cov3["n_covered"],
        "cov_per_unit": cov_per_unit,
        "skel_dist": skel_dist,
        "cos_dist": cos_dist,
        "fulfill": (sum(hits) / len(hits)) if hits else None,
        "n_audit": len(hits),
        "vague_rate": (sum(vague) / len(vague)) if vague else None,
        "actionable": (sum(action) / len(action)) if action else None,
        "on_topic": (sum(on_topic) / len(on_topic)) if on_topic else None,
        "neg_rate": neg,
        "chars": chars,
        "mean_unit_chars": chars / len(units),
    }


def mean_pairwise_cos(texts) -> float:
    """阈值无关的「同题内思路差异」：两两 TF-IDF 余弦距离的均值。

    ⚠️ 事后探索性指标：预注册的 modality（聚类簇数）在本数据上无方差，
    按预注册 §5 判「该指标失效」；本指标是补充，不替代预注册判决。
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    texts = [t for t in texts if (t or "").strip()]
    if len(texts) < 2:
        return float("nan")
    vec = TfidfVectorizer(tokenizer=measure._char_tokens, analyzer="word", token_pattern=None, lowercase=False)
    X = vec.fit_transform(texts)
    D = 1.0 - cosine_similarity(X)
    n = D.shape[0]
    ds = [D[i, j] for i in range(n) for j in range(i + 1, n)]
    return sum(ds) / len(ds) if ds else float("nan")


def pooled_modality(arm, tid, rep_units, n=3):
    """匹配 n 的模态数：跨臂只在同 n 上比。"""
    pool = []
    for rp in sorted(rep_units):
        pool.extend(rep_units[rp])
    if len(pool) < n:
        return None
    return measure.modality_count(pool[:n])


def decide(metric, armA, armB, topic_ids, stat):
    """预注册 §5 的判决公式。stat 是可注入的统计函数（便于变异注入自检）。"""
    details = []
    for tid in topic_ids:
        a = stat(armA, tid, metric)
        b = stat(armB, tid, metric)
        if a["mean"] is None or b["mean"] is None:
            details.append({"topic": tid, "diff": None, "note": "无读数（该臂此指标不适用）"})
            continue
        diff = a["mean"] - b["mean"]
        floor = max(a["sd"] or 0.0, b["sd"] or 0.0)
        details.append({
            "topic": tid, "A": a["mean"], "B": b["mean"], "diff": diff,
            "sdA": a["sd"], "sdB": b["sd"], "floor": floor,
            "sign_ok": diff > 0, "exceeds": diff > floor,
        })
    usable = [d for d in details if d.get("diff") is not None]
    n = len(usable)
    if n == 0:
        return {"verdict": "无数据", "details": details}
    pos = sum(1 for d in usable if d["diff"] > 0)
    exc = sum(1 for d in usable if d["exceeds"])
    mean_diff = sum(d["diff"] for d in usable) / n
    thr = math.ceil(2 / 3 * n)
    ok = (mean_diff > 0) and (pos >= thr) and (exc >= thr)
    return {
        "verdict": "成立" if ok else "不成立",
        "mean_diff": mean_diff, "pos": pos, "n": n, "exceeds": exc, "threshold": thr,
        "details": details,
    }


def main(run_dir: str, out_dir: str | None = None):
    run = Path(run_dir)
    out = Path(out_dir) if out_dir else run
    out.mkdir(parents=True, exist_ok=True)
    topics = load_topics()
    topics_by_id = {t["id"]: t for t in topics}
    recs = load(run)
    pack, aud, skl, skl2 = build_units(recs, topics_by_id)

    # 通道健康度（必须报，不静默）
    health = {}
    for r in recs:
        p = r["phase"]
        h = health.setdefault(p, {"n": 0, "ok": 0, "trunc": 0, "fail": 0, "parse_err": 0})
        h["n"] += 1
        if r.get("ok"):
            h["ok"] += 1
        if r.get("truncated"):
            h["trunc"] += 1
        if not r.get("ok"):
            h["fail"] += 1
        if r.get("parse_error"):
            h["parse_err"] += 1

    # 逐 (arm, topic, rep)
    rows = []
    for (arm, tid, rep) in sorted(pack):
        m = per_rep_metrics(arm, tid, rep, pack[(arm, tid, rep)], aud, skl, skl2, topics_by_id)
        if m:
            rows.append(m)

    # 臂 × 题 聚合（mean / sd over reps）
    agg = {}
    for r in rows:
        agg.setdefault((r["arm"], r["topic"]), []).append(r)

    SPECIAL = {}  # (arm, topic, metric) -> {"mean","sd","n"}：无法按 rep 聚合的特殊口径

    def stat(arm, tid, key):
        sp = SPECIAL.get((arm, tid, key))
        if sp:
            return sp
        vals = [r[key] for r in agg.get((arm, tid), [])
                if r.get(key) is not None and not (isinstance(r[key], float) and math.isnan(r[key]))]
        if not vals:
            return {"mean": None, "sd": None, "n": 0, "vals": []}
        m = sum(vals) / len(vals)
        sd = statistics.stdev(vals) if len(vals) > 1 else 0.0
        return {"mean": m, "sd": sd, "n": len(vals), "vals": vals}

    open_ids = [t["id"] for t in topics if t.get("type") == "open"]
    collapsed_ids = [t["id"] for t in topics if t.get("type") == "collapsed"]

    # A0 特殊口径：每 rep 只有 1 条思路 ⇒ 组内距离无意义。
    # 它的"宽度"就是【同题重复采样之间的距离】——正好是仪器在该题上的噪声地板。
    for tid in [t["id"] for t in topics]:
        reps = sorted(rep for (a, tt, rep) in pack if a == "A0" and tt == tid)
        texts = [pack[("A0", tid, rp)]["units"][0] for rp in reps
                 if pack.get(("A0", tid, rp)) and pack[("A0", tid, rp)]["units"]]
        if len(texts) < 2:
            continue
        skels = []
        for rp in reps:
            if not pack.get(("A0", tid, rp)):
                continue
            for m in pack[("A0", tid, rp)]["meta"]:
                s_ = unit_skeleton("A0", tid, rp, m, skl, skl2)
                if s_:
                    skels.append(s_["skeleton"])
        if len(skels) < 2:
            continue
        pairs = []
        for i in range(len(skels)):
            for j in range(i + 1, len(skels)):
                d = measure.skeleton_distance([skels[i], skels[j]])
                if not (isinstance(d, float) and math.isnan(d)):
                    pairs.append(d)
        if pairs:
            SPECIAL[("A0", tid, "skel_dist")] = {
                "mean": sum(pairs) / len(pairs),
                "sd": statistics.stdev(pairs) if len(pairs) > 1 else 0.0,
                "n": len(pairs), "vals": pairs,
            }

    # 匹配 n=3 的模态数
    for arm in ARMS:
        for tid in [t["id"] for t in topics]:
            rp = {rep: pack[(arm, tid, rep)]["units"] for rep in range(3) if (arm, tid, rep) in pack}
            v = pooled_modality(arm, tid, rp, 3)
            if v is not None:
                for r in agg.get((arm, tid), []):
                    r["modality_n3"] = v

    # ---- 判决（prereg §5）----
    preds = [
        ("P1", "skel_dist", "A3", "A1", open_ids, "TSC 的机制骨架比身份臂更分散"),
        ("P2", "fulfill", "A3", "A1", open_ids, "TSC 的兑现率高于身份臂"),
        ("P3", "skel_dist", "A3", "A2", open_ids, "TSC 比单提示多视角更分散"),
        ("P4", "skel_dist", "A3", "A0", open_ids, "TSC 比基线更分散"),
        ("P5", "cov", "A3", "A3c", open_ids, "自测绘分支的覆盖不比外部给定轴差"),
        ("P6", "skel_dist", "A3", "A4", open_ids, "H0：任务相关路径选择优于任务无关维度"),
        ("P7", "skel_dist", "A3", "A0", collapsed_ids, "负对照：路径唯一题上 TSC 不应展宽"),
    ]
    verdicts = {}
    for pid, metric, a, b, tids, desc in preds:
        verdicts[pid] = {"metric": metric, "A": a, "B": b, "desc": desc, **decide(metric, a, b, tids, stat)}

    # 次指标口径（cov / cov250 / cov3 都是预注册 §4.2 的读数，不是新指标）
    # 目的：主指标饱和时，用【仍然有效的那把尺子】做同题对打
    SECOND = [
        ("S1", "cov", "A3", "A1", open_ids, "次指标：TSC 自测绘 vs 身份臂（轴覆盖）"),
        ("S2", "cov3", "A3", "A1", open_ids, "次指标·同 n 配平：TSC 自测绘 vs 身份臂"),
        ("S3", "cov3", "A3", "A2", open_ids, "次指标·同 n 配平：TSC 自测绘 vs 单提示多视角"),
        ("S4", "cov3", "A3", "A0", open_ids, "次指标·同 n 配平：TSC 自测绘 vs 基线"),
        ("S5", "cov3", "A3", "A4", open_ids, "次指标·同 n 配平：H0 杀手——TSC vs 任务无关维度"),
        ("S6", "cov3", "A1", "A0", open_ids, "次指标·同 n 配平：身份臂 vs 基线"),
        ("S7", "cov3", "A2", "A0", open_ids, "次指标·同 n 配平：单提示多视角 vs 基线"),
        ("S8", "cov3", "A4", "A0", open_ids, "次指标·同 n 配平：H0 臂 vs 基线"),
        ("S9", "cov3", "A3c", "A0", open_ids, "次指标·同 n 配平：外部给定轴 vs 基线（机制上界）"),
        ("S10", "cov3", "A3c", "A1", open_ids, "次指标·同 n 配平：外部给定轴 vs 身份臂"),
        ("S11", "cov3", "A3", "A0", collapsed_ids, "负对照·同 n 配平：路径唯一题上 TSC 不应展宽"),
        ("S12", "cov250", "A3", "A1", open_ids, "次指标·长度配平 250 字：TSC vs 身份臂"),
        # ★★ Round 2 新增对比（★ 判决公式与 v1 完全一致、★ 不事后调 ★）★★
        ("S13", "cov3", "A5", "A4b", open_ids, "★★ 主对比：skill 完整规程 vs 同轴库裸给（★ 改写+签名+代价 的净贡献 ★）★★"),
        ("S14", "cov3", "A5", "A3c", open_ids, "次指标：skill 规程 vs 外部给定任务特异轴（上界）"),
        ("S15", "cov3", "A5", "A0", open_ids, "次指标：skill 规程 vs 基线"),
        ("S16", "cov3", "A4b", "A0", open_ids, "次指标：同轴库裸给 vs 基线（★ 检验【轴库规模】本身的贡献 ★）"),
        ("S17", "cov3", "A5", "A4", open_ids, "次指标：skill 规程 vs 6 条任务无关维度臂"),
        ("S18", "cov3", "A5", "A0", collapsed_ids, "★★ 负对照：路径唯一题上 skill 不应展宽（★ 证伪 ⇒ 装置无效 ★）★★"),
        ("S19", "cov3", "A4b", "A0", collapsed_ids, "负对照：同轴库裸给在路径唯一题上也不应展宽"),
    ]
    for pid, metric, a2, b2, tids2, desc2 in SECOND:
        verdicts[pid] = {"metric": metric, "A": a2, "B": b2, "desc": desc2,
                         **decide(metric, a2, b2, tids2, stat)}

    # ---- 写表 ----
    md = []
    md.append("# 实验读数表（main1）\n")
    md.append("## 0. 通道健康度（失败不静默归零）\n")
    md.append("| 阶段 | 调用数 | 成功 | 失败 | 截断 | 解析失败 | 成功率 |")
    md.append("|---|--:|--:|--:|--:|--:|--:|")
    for p, h in sorted(health.items()):
        md.append(f"| {p} | {h['n']} | {h['ok']} | {h['fail']} | {h['trunc']} | {h['parse_err']} | {h['ok']/max(1,h['n']):.3f} |")

    md.append("\n## 1. 臂级总览（开放题 6 道，3 rep）\n")
    md.append("| 臂 | 思路/题 | cov3(同n)↑ | cov↑ | cov250↑ | cos_dist↑ | 每思路覆盖↑ | fulfill | skel_dist | modality | actionable | 字数 | 邻接标记/千字↓ |")
    md.append("|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|")
    for arm in ARMS:
        acc = {}
        for key in ["skel_dist", "cov", "cov250", "cov3", "cov_per_unit", "cos_dist", "fulfill", "vague_rate", "actionable", "on_topic", "chars", "neg_rate", "modality_n3"]:
            vals = []
            for tid in open_ids:
                s = stat(arm, tid, key)
                if s["mean"] is not None:
                    vals.append(s["mean"])
            acc[key] = sum(vals) / len(vals) if vals else None
        n_units = sum(stat(arm, tid, "n_units")["mean"] or 0 for tid in open_ids) / max(1, len(open_ids))
        def f(v, d=3):
            return "—" if v is None else f"{v:.{d}f}"
        md.append(
            f"| {arm} {ARMS_CN[arm]} | {n_units:.1f} | {f(acc['cov3'],2)} | "
            f"{f(acc['cov'],2)} | {f(acc['cov250'],2)} | {f(acc['cos_dist'])} | {f(acc['cov_per_unit'],2)} | "
            f"{f(acc['fulfill'])} | {f(acc['skel_dist'])} | {f(acc['modality_n3'],2)} | "
            f"{f(acc['actionable'],2)} | {f(acc['chars'],0)} | {f(acc['neg_rate'],2)} |"
        )

    md.append("\n## 2. 逐题：skel_dist（主指标）\n")
    md.append("| 题 | " + " | ".join(f"{a}" for a in ARMS) + " |")
    md.append("|---|" + "---|" * len(ARMS))
    for tid in [t["id"] for t in topics]:
        cells = []
        for arm in ARMS:
            s = stat(arm, tid, "skel_dist")
            cells.append("—" if s["mean"] is None else f"{s['mean']:.3f}±{(s['sd'] or 0):.3f}")
        md.append(f"| {tid} | " + " | ".join(cells) + " |")

    md.append("\n## 3. 逐题：cov（预注册轴覆盖，开放题满分 5）\n")
    md.append("| 题 | " + " | ".join(f"{a}" for a in ARMS) + " |")
    md.append("|---|" + "---|" * len(ARMS))
    for tid in [t["id"] for t in topics]:
        cells = []
        for arm in ARMS:
            s = stat(arm, tid, "cov")
            cells.append("—" if s["mean"] is None else f"{s['mean']:.2f}")
        md.append(f"| {tid} | " + " | ".join(cells) + " |")

    md.append("\n## 4. 逐题：fulfill（兑现率）\n")
    md.append("| 题 | " + " | ".join(f"{a}" for a in ARMS) + " |")
    md.append("|---|" + "---|" * len(ARMS))
    for tid in [t["id"] for t in topics]:
        cells = []
        for arm in ARMS:
            s = stat(arm, tid, "fulfill")
            cells.append("—" if s["mean"] is None else f"{s['mean']:.2f}")
        md.append(f"| {tid} | " + " | ".join(cells) + " |")

    md.append("\n## 4b. 指标分辨力体检（哪个尺子还活着）\n")
    md.append("| 指标 | 各臂均值范围 | 有无组间方差 | 判读 |")
    md.append("|---|---|---|---|")
    for key, label in [("skel_dist", "skel_dist（预注册主指标）"), ("fulfill", "fulfill（兑现率）"),
                       ("modality_n3", "modality(n=3)（预注册辅指标）"), ("cov", "cov（预注册次指标）"),
                       ("cov250", "cov250（预注册次指标·长度配平）"), ("cov3", "cov3（同 n 配平）"),
                       ("cos_dist", "cos_dist（事后探索·阈值无关）")]:
        vals = []
        for arm in ARMS:
            for tid in open_ids:
                st = stat(arm, tid, key)
                if st["mean"] is not None:
                    vals.append(st["mean"])
        if not vals:
            md.append(f"| {label} | — | 无读数 | 指标不可用 |")
            continue
        lo, hi = min(vals), max(vals)
        spread = hi - lo
        alive = "有" if spread > 1e-9 else "无（饱和/恒定）"
        note = "**饱和，判据失效**" if spread <= 1e-9 else ("方差很小，可分辨性弱" if spread < 0.05 else "有分辨力")
        md.append(f"| {label} | {lo:.4f} – {hi:.4f} | {alive} | {note} |")

    md.append("\n## 5. 判决（prereg §5 公式）\n")
    md.append("\n### 5a. 主/原预测（指标饱和者一律判「无法判定」，不得当作被证伪）\n")
    md.append("| 预测 | 内容 | 指标 | 对比 | 均值差 | 同向题数 | 超地板题数 | 裁决 |")
    md.append("|---|---|---|---|--:|--:|--:|---|")
    for pid in [p[0] for p in preds]:
        v = verdicts[pid]
        md_diff = "—" if v.get("mean_diff") is None else f"{v['mean_diff']:.4f}"
        md.append(
            f"| {pid} | {v['desc']} | {v['metric']} | {v['A']} vs {v['B']} | "
            f"{md_diff} | {v.get('pos','—')}/{v.get('n','—')} | {v.get('exceeds','—')}/{v.get('n','—')} | **{v['verdict']}** |"
        )
    md.append("\n### 5b. 次指标口径（cov / cov250 / cov3，均为预注册 §4.2 的读数）\n")
    md.append("| 编号 | 内容 | 指标 | 对比 | 均值差 | 同向题数 | 超地板题数 | 裁决 |")
    md.append("|---|---|---|---|--:|--:|--:|---|")
    for pid, _, _, _, _, _ in SECOND:
        v = verdicts[pid]
        md_diff = "—" if v.get("mean_diff") is None else f"{v['mean_diff']:.4f}"
        md.append(
            f"| {pid} | {v['desc']} | {v['metric']} | {v['A']} vs {v['B']} | "
            f"{md_diff} | {v.get('pos','—')}/{v.get('n','—')} | {v.get('exceeds','—')}/{v.get('n','—')} | **{v['verdict']}** |"
        )

    md.append("\n### 逐题明细\n")
    for pid in [p[0] for p in preds]:
        v = verdicts[pid]
        md.append(f"\n**{pid}** — {v['desc']}（{v['metric']}, {v['A']} vs {v['B']}）\n")
        md.append("| 题 | A | B | 差 | sdA | sdB | 地板 | 同向 | 超地板 |")
        md.append("|---|--:|--:|--:|--:|--:|--:|:-:|:-:|")
        for d in v["details"]:
            if d.get("diff") is None:
                md.append(f"| {d['topic']} | — | — | — | — | — | — | — | {d.get('note','')} |")
            else:
                md.append(
                    f"| {d['topic']} | {d['A']:.4f} | {d['B']:.4f} | {d['diff']:+.4f} | "
                    f"{(d['sdA'] or 0):.4f} | {(d['sdB'] or 0):.4f} | {d['floor']:.4f} | "
                    f"{'✓' if d['sign_ok'] else '✗'} | {'✓' if d['exceeds'] else '✗'} |"
                )

    (out / "tables.md").write_text("\n".join(md), encoding="utf-8")
    (out / "readings.json").write_text(json.dumps(
        {"health": health, "rows": rows, "verdicts": verdicts}, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8")
    print("\n".join(md))
    print(f"\n-> {out/'tables.md'}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "runs/main1")
