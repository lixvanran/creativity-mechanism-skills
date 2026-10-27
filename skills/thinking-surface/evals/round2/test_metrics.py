"""指标与判据的变异注入自检。

纪律：任何「会红的检查」都必须能被证明在**该红的时候红**。
否则「全绿」可能只是恒真。

本文件构造一批"应当报错/应当分离"的样本，断言检查器确实报错。
退出码 0 = 全部按预期反应；1 = 有检查项失灵（恒真）。
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import measure  # noqa: E402
from check_topics import check, load_topics  # noqa: E402

FAILS: list[str] = []


def expect(cond, label):
    if cond:
        print(f"  ✓ {label}")
    else:
        print(f"  ✗ {label}")
        FAILS.append(label)


def t_coverage():
    print("[覆盖判据]")
    topics = load_topics()
    t1 = next(t for t in topics if t["id"] == "T1")
    a1 = next(a for a in t1["axes"] if a["id"] == "T1.a")
    # 命中 2/3 must、无 forbid ⇒ 覆盖
    txt_ok = "这次活动以选书为起点，安排共读与书目推荐，读书会也同步进行。"
    r = measure.axis_hits(a1, txt_ok)
    expect(r["covered"] is True, f"命中 2/3 must 时应判覆盖（实际 hit={r['hit_must']}）")
    # 只命中 1/3 ⇒ 不覆盖
    txt_1 = "这次只聊了书目，没别的。"
    r1 = measure.axis_hits(a1, txt_1)
    expect(r1["covered"] is False, f"只命中 1/3 must 时应判不覆盖（实际 hit={r1['hit_must']}）")
    # 命中 forbid ⇒ 不覆盖（即使 must 全中）
    txt_forbid = "选书、共读、书目都安排上了，还要用打卡积分做激励。"
    r2 = measure.axis_hits(a1, txt_forbid)
    expect(r2["covered"] is False, f"命中 forbid 时应判不覆盖（实际 forbid={r2['hit_forbid']}）")
    # 长度配平版：把 must 词推到 250 字之后 ⇒ 应不覆盖
    long_txt = "无关内容。" * 80 + "选书 共读 书目"
    r3 = measure.axis_hits(a1, long_txt[:250])
    expect(r3["covered"] is False, "截断到 250 字后尾部 must 词应被切掉（长度配平生效）")


def t_modality():
    print("[模态数]")
    same = ["设计方案的第一步是先做调研然后执行。"] * 3
    diff = [
        "通过积分排行榜和奖励机制驱动全员参与。",
        "组织同伴共读小组，每天围绕一个问题讨论并记录观点。",
        "在图书馆现场布置展区与动线，安排装置与快闪体验。",
    ]
    m_same = measure.modality_count(same)
    m_diff = measure.modality_count(diff)
    expect(m_same == 1, f"三条同义文本应聚成 1 模态（实际 {m_same}）")
    expect(m_diff > m_same, f"三条异质文本应多于 1 模态（实际 {m_diff} vs {m_same}）")
    expect(measure.modality_count([]) == 0, "空集应返回 0 而不是报错")
    expect(measure.modality_count(["只有一条"]) == 1, "单条应返回 1")


def t_skeleton():
    print("[骨架距离]")
    d_same = measure.skeleton_distance([["积分", "排名"], ["积分", "排名"]])
    d_diff = measure.skeleton_distance([["积分", "排名"], ["共读", "读书会"]])
    expect(abs(d_same) < 1e-9, f"同骨架距离应为 0（实际 {d_same}）")
    expect(d_diff > 0.9, f"不相交骨架距离应接近 1（实际 {d_diff}）")
    expect(measure.skeleton_distance([["a"]]) != measure.skeleton_distance([["a"]]), "单样本不应被当成 0")
    import math
    expect(math.isnan(measure.skeleton_distance([["a"]])), "单样本应返回 nan（不静默填 0）")


def t_split():
    print("[思路切分]")
    multi = (
        "### 方案一：闯关制\n" + "内容甲。" * 30 + "\n" +
        "### 方案二：共读制\n" + "内容乙。" * 30 + "\n" +
        "### 方案三：工作坊\n" + "内容丙。" * 30 + "\n" +
        "### 方案四：数字策展\n" + "内容丁。" * 30 + "\n" +
        "### 综合说明\n" + "综合起来看甲乙丙丁。" * 10
    )
    units, note = measure.split_ideas(multi, strict=True)
    expect(note == "split" and len(units) == 4, f"应切成 4 条（实际 note={note} n={len(units)}）")
    expect(all("综合起来看" not in u for u in units), "综合段不应混进任何一条思路")
    single = "方案要点：\n1. 先做调研\n2. 再做试点\n3. 最后推广\n" + "细节说明。" * 40
    u2, n2 = measure.split_ideas(single, strict=True)
    expect(n2 == "unsplit" and len(u2) == 1, f"单方案的编号步骤不应被切成多条（实际 n2={n2} n={len(u2)}）")
    ns = measure.count_sections(single, strict=False)
    expect(ns >= 3, f"宽松模式应能看出编号分节（诊断用）（实际 {ns}）")


def t_leak_gate():
    print("[泄题闸门]")
    topics = load_topics()
    base = check(topics)
    expect(base == [], f"当前题集应无泄漏（实际 {base}）")
    # 变异 1：把评分词塞进轴描述
    bad = copy.deepcopy(topics)
    bad[0]["axes"][0]["feed"] += " 选书"
    e1 = check(bad)
    expect(any("L1" in x for x in e1), f"塞 must 词进 feed 应被 L1 抓住（实际 {e1}）")
    # 变异 2：把评分词塞进题面
    bad2 = copy.deepcopy(topics)
    bad2[1]["prompt"] += " 请多想想线路。"
    e2 = check(bad2)
    expect(any("L3" in x for x in e2), f"塞 must 词进题面应被 L3 抓住（实际 {e2}）")
    # 变异 3：跨轴串味
    bad3 = copy.deepcopy(topics)
    bad3[0]["axes"][1]["feed"] += " 选书"
    e3 = check(bad3)
    expect(any("L2" in x for x in e3), f"跨轴串味应被 L2 抓住（实际 {e3}）")


def t_neg_marker():
    print("[表演性标记]")
    v = measure.neg_marker_rate("我打算换个角度，从多个维度综合考虑，既要快又要好。" * 5)
    v0 = measure.neg_marker_rate("先在三个小区试点投放点改造，安排督导值班。" * 5)
    expect(v > 0, f"含表演性表述应有非零标记率（实际 {v}）")
    expect(v0 == 0, f"无表演性表述应为零（实际 {v0}）")


def t_decision_rule():
    print("[判决公式]")
    import analyze

    def fake_stat(arm, tid, key):
        vals = []
        for r in ROWS:
            if r["arm"] == arm and r["topic"] == tid and r.get(key) is not None:
                vals.append(r[key])
        if not vals:
            return {"mean": None, "sd": None, "n": 0, "vals": []}
        import statistics
        m = sum(vals) / len(vals)
        sd = statistics.stdev(vals) if len(vals) > 1 else 0.0
        return {"mean": m, "sd": sd, "n": len(vals), "vals": vals}

    topics = [t["id"] for t in load_topics() if t.get("type") == "open"]

    # 构造 1：X 恒等于 Y ⇒ 必须判不成立（若判成立说明判决逻辑恒真）
    ROWS = []
    for tid in topics:
        for rep in range(3):
            ROWS.append({"arm": "A3", "topic": tid, "rep": rep, "skel_dist": 0.5})
            ROWS.append({"arm": "A1", "topic": tid, "rep": rep, "skel_dist": 0.5})
    v = analyze.decide("skel_dist", "A3", "A1", topics, fake_stat)
    expect(v["verdict"] == "不成立", f"完全相同的两臂不得判「成立」（实际 {v['verdict']}）")

    # 构造 2：X 明显更大且无方差 ⇒ 应判成立
    ROWS = []
    for tid in topics:
        for rep in range(3):
            ROWS.append({"arm": "A3", "topic": tid, "rep": rep, "skel_dist": 0.9})
            ROWS.append({"arm": "A1", "topic": tid, "rep": rep, "skel_dist": 0.2})
    v2 = analyze.decide("skel_dist", "A3", "A1", topics, fake_stat)
    expect(v2["verdict"] == "成立", f"明显更大时应判「成立」（实际 {v2['verdict']}）")

    # 构造 3：只有少数题同向 ⇒ 必须不成立
    ROWS = []
    for i, tid in enumerate(topics):
        for rep in range(3):
            hi = 0.9 if i < 2 else 0.1
            ROWS.append({"arm": "A3", "topic": tid, "rep": rep, "skel_dist": hi})
            ROWS.append({"arm": "A1", "topic": tid, "rep": rep, "skel_dist": 0.5})
    v3 = analyze.decide("skel_dist", "A3", "A1", topics, fake_stat)
    expect(v3["verdict"] == "不成立", f"仅少数题同向时必须判「不成立」（实际 {v3['verdict']}）")

    # 构造 4：差值小于噪声地板（每题方差大）⇒ 必须不成立
    ROWS = []
    for tid in topics:
        for rep in range(3):
            jitter = [0.4, 1.0, 0.4][rep]
            ROWS.append({"arm": "A3", "topic": tid, "rep": rep, "skel_dist": jitter})
            ROWS.append({"arm": "A1", "topic": tid, "rep": rep, "skel_dist": 0.5})
    v4 = analyze.decide("skel_dist", "A3", "A1", topics, fake_stat)
    expect(v4["verdict"] == "不成立", f"差值小于噪声地板时必须判「不成立」（实际 {v4['verdict']}）")


def main() -> int:
    for fn in [t_coverage, t_modality, t_skeleton, t_split, t_leak_gate, t_neg_marker, t_decision_rule]:
        fn()
    print()
    if FAILS:
        print(f"FAIL: {len(FAILS)} 项检查失灵（可能恒真）：")
        for f in FAILS:
            print("  -", f)
        return 1
    print("OK: 全部变异注入按预期被抓住")
    return 0


if __name__ == "__main__":
    sys.exit(main())
