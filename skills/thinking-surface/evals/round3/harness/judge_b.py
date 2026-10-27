# -*- coding: utf-8 -*-
"""judge_b.py —— 路 B 的分析器（★ 全部机械、★ 免判官 ★）

★ 读数（★ 全部在【分支并集】与【合流输出】两个口径上各算一遍 ★）：
  abs_rate   缺席率 = 1 − 覆盖维度数/10          ★ 主指标
  cov_n      覆盖维度数
  off_rate   跨域率（"进大厂"等）
  boot_rec   自举召回率（★ B2 自举的实体类别 ∩ 金标维度 ★）—— 只对 B2 适用
  cost       调用数 / 字数 / token

★ 比较：★ rep 级配对（★ 同题同 rep、★ B1 vs B2、★ 3 个配对 ★）
  1) 配对均值差
  2) 配对置换检验（★ 10,000 次符号翻转、★ 两尾 ★）★ 借 arXiv:2604.19457 的统计协议 ★
  3) bootstrap 95% CI
★ ★ 3 个配对 ⇒ ★ CI 很宽、★ 报告时必须如实说 ★
"""
from __future__ import annotations
import collections, json, math, os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dimjudge

TOPICS = {t["id"]: t for t in json.load(open(os.path.join(HERE, "..", "topics.json"), encoding="utf-8"))}


def load(run_dir):
    p = os.path.join(run_dir, "calls.jsonl")
    rows = []
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def units_by_arm(rows):
    """(arm, topic, rep) -> {gen:[texts], merge:text|None, base:text|None, entities:[...]}"""
    out = collections.defaultdict(lambda: {"gen": [], "merge": None, "base": None, "entities": []})
    for r in rows:
        key = (r["arm"], r["topic"], r["rep"])
        ph = r["phase"]
        if not r.get("ok"):
            continue
        if ph == "GEN":
            out[key]["gen"].append(r.get("text") or "")
        elif ph == "MERGE":
            out[key]["merge"] = r.get("text") or ""
        elif ph == "BASE":
            out[key]["base"] = r.get("text") or ""
        elif ph == "ENT":
            import parse_b
            cats, _ = parse_b.extract_entities(r.get("parsed"), r.get("text"))
            out[key]["entities"] = cats
    return out


def boot_recall(topic, entities):
    """★ 自举召回率 = 自举类别命中的金标维度数 / 金标维度总数 ★"""
    if not entities:
        return None, []
    names = [e.get("category") or "" for e in entities]
    hit = []
    for ax in topic["axes"]:
        keys = ax.get("match_keys") or []
        if any(k in n for n in names for k in keys):
            hit.append(ax["id"])
    return len(hit) / len(topic["axes"]), hit


def metrics_for(topic, pack):
    gen = pack["gen"]
    m = {"n_gen": len(gen)}
    if gen:
        joined = "\n".join(gen)
        ar, cov = dimjudge.absent_rate(topic, joined)
        m["abs_rate_gen"] = ar
        m["cov_n_gen"] = len(cov)
        m["off_gen"] = 1.0 if dimjudge.offdomain_hit(topic, joined) else 0.0
    if pack["base"]:
        ar, cov = dimjudge.absent_rate(topic, pack["base"])
        m["abs_rate_base"] = ar
        m["cov_n_base"] = len(cov)
        m["off_base"] = 1.0 if dimjudge.offdomain_hit(topic, pack["base"]) else 0.0
    if pack["merge"]:
        ar, cov = dimjudge.absent_rate(topic, pack["merge"])
        m["abs_rate_merge"] = ar
        m["cov_n_merge"] = len(cov)
    br, hit = boot_recall(topic, pack["entities"])
    if br is not None:
        m["boot_recall"] = br
        m["boot_hit"] = hit
    return m


def perm_test(diffs, n=10000, seed=20261027):
    """★ 配对置换检验（★ 符号翻转、★ 两尾 ★）★"""
    rng = random.Random(seed)
    k = len(diffs)
    if k == 0:
        return None
    obs = abs(sum(diffs) / k)
    hits = 0
    for _ in range(n):
        s = sum(d if rng.random() < 0.5 else -d for d in diffs) / k
        if abs(s) >= obs - 1e-12:
            hits += 1
    return {"p_two_sided": hits / n, "n_perm": n, "obs": obs}


def boot_ci(diffs, n=10000, seed=20261027):
    rng = random.Random(seed)
    k = len(diffs)
    if k == 0:
        return None
    means = []
    for _ in range(n):
        s = sum(rng.choice(diffs) for _ in range(k)) / k
        means.append(s)
    means.sort()
    return {"lo95": means[int(0.025 * n)], "hi95": means[int(0.975 * n) - 1]}


def main(run_dir):
    rows = load(run_dir)
    packs = units_by_arm(rows)
    topics = TOPICS
    res = []
    for (arm, tid, rep), pack in sorted(packs.items()):
        t = topics[tid]
        m = metrics_for(t, pack)
        m.update({"arm": arm, "topic": tid, "rep": rep})
        res.append(m)
    # ---- 打印逐 rep 明细 ----
    print("═══ 逐 rep 明细 ═══")
    for m in res:
        print("  %-4s %-4s rep%s  分支并集: 缺席=%.0f%% 覆盖=%d 跨域=%s | 合流: 缺席=%s | 自举召回=%s"
              % (m["arm"], m["topic"], m["rep"], 100 * m.get("abs_rate_gen", float('nan')),
                 m.get("cov_n_gen", -1), m.get("off_gen"),
                 ("%.0f%%" % (100 * m["abs_rate_merge"])) if "abs_rate_merge" in m else "—",
                 ("%.0f%%" % (100 * m["boot_recall"])) if "boot_recall" in m else "—"))
    # ---- 臂间配对比较 ----
    print("\n═══ 臂间配对比较（★ 同题同 rep ★）═══")
    out = {}
    for A, B in (("B1", "B2"), ("B0", "B2"), ("B0", "B1"), ("B1", "B2")):
        for metric, better in (("abs_rate_gen", "low"), ("abs_rate_merge", "low"), ("off_gen", "low")):
            pairs = []
            for (arm, tid, rep), m in [(k, v) for k, v in zip([k for k in sorted(packs)], [packs[k] for k in sorted(packs)])]:
                if arm != A:
                    continue
                mb = packs.get((B, tid, rep))
                if not mb:
                    continue
                ma = metrics_for(topics[tid], m)
                mbb = metrics_for(topics[tid], mb)
                if metric in ma and metric in mbb:
                    d = ma[metric] - mbb[metric]
                    if better == "low":
                        d = -d            # ★ 转成"越大越好" ★
                    pairs.append(d)
            if not pairs:
                continue
            mean = sum(pairs) / len(pairs)
            pt = perm_test(pairs)
            ci = boot_ci(pairs)
            key = "%s>%s:%s" % (A, B, metric)
            out[key] = {"pairs": pairs, "mean_diff": mean, "perm": pt, "ci": ci}
            print("  %-22s n=%d 配对均值差=%+.3f  置换p=%.3f  95%%CI=[%+.3f, %+.3f]  %s"
                  % (key, len(pairs), mean, pt["p_two_sided"], ci["lo95"], ci["hi95"],
                     "★支持★" if pt["p_two_sided"] < 0.05 else "不显著"))
    with open(os.path.join(run_dir, "judge_b.json"), "w", encoding="utf-8") as f:
        json.dump({"rows": res, "comparisons": out}, f, ensure_ascii=False, indent=1)
    print("\n  → %s" % os.path.join(run_dir, "judge_b.json"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "runs", "b1")))
