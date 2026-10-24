"""★ **状态层规格的离线测试（★ 第二组出规格，★ 第四组按规格实现测试）**

> ★ **接口归属：第二组。** ★ **本文件是【规格的可执行形态】** ⇒ ⇒
> ★ **改规则 ⇒ ⇒ 测试必须失败**（★ 否则测试是假绿）。
>
> ★ **运行**：`python3 -B creativity_lab/experiments/test_state_layer.py`（★ **exit 0 = 全过**）｜★ **零 API**
> ★ **自检**：`python3 -B creativity_lab/experiments/test_state_layer.py --self-test`
>   ⇒ ★ **对规则注入变异 ⇒ ⇒ 断言【对应的那一项测试】必须失败** ⇒ ⇒ 证明每个测试项都是活的。
>
> ★ **纪律**：
> ★ ① **负向断言是必需的** —— ★ 只测 happy path 的测试会放过"该发生的没发生"。
> ★ ② **零 API / 零依赖** —— ★ 单元测试不需要任何外部依赖。
> ★ ③ ★ **失败路径必须显式** —— ★ 断言失败必须响亮（打印 + 非零 exit code），★ 不许静默通过。
>
> ★ **★ 与第二组原文的关系（★ 证据等级说明，★ 别当成逐字节一致）**：
> ★ 第二组直发的 `state_layer.py` 是**逐字节原文**（★ **rev1** sha256 = `69a29c506a4e4ab0`，★ 已核）。
> ★ **本测试文件是第四组按第二组给出的【测试规格表】实现** ⇒ ⇒
> ★ **它的 sha256 必然与第二组仓内那份不同** ⇒ ⇒ ★ **不能声称"逐字节一致"**，
> ★ 只能说"**规格覆盖等价 + 变异注入自证**"。
>
> ★★★ **【rev1 · 2026-10-25 · 第二组裁决 4 条差异后】★★★**
> ★ **接口版本**：`creativity_lab/state_layer.py` sha256 = `69a29c506a4e4ab0`（rev1）
> ★ **rev0** sha256 = `38795bf6adfdee05`（★ 已被 rev1 取代）
> ★ **本文件 8 项** = ★ 第二组 6 项（★ T1–T5 + 三个 bug 回归）★ + 第四组 2 项
>   （★ `test6_spec_redlines` 规格三条红线 + ★ `test7_detect_tie` 并列检测）
> ★ ⇒ ★ **两边互补，不互相替换**。
> ★ ★ **★ 关键教训（★ 本文件最重要的一条）**：
> ★ **rev0 的 5 项测试全绿，但 rev0 有 3 个真 bug** ⇒ ⇒ ★ **「离线全绿」≠「语义无歧义」**
> ★ ⇒ ⇒ ★ **根因**：★ 「连续 vs 累计」两种语义**都能通过 rev0 的同一套测试** ⇒ ⇒
> ★ ⇒ ★ **⇒ 每修一个 bug，必须补一条【只有新实现才通过】的断言**（★ 现由 `test8_rev1_regressions` 承担）
> ★ ⇒ ⇒ ★ **⇒ 且每条断言都要有对应的变异注入**（★ 现由 `--self-test` 的 m7/m8/m9/m10 承担）。
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import os
import sys
import tempfile

# ★ 把仓库根放进 sys.path ⇒ ⇒ 直接 `python3 -B creativity_lab/experiments/test_state_layer.py`
# ★ 也能 import 到 `creativity_lab`（★ 否则 sys.path[0] 是本目录 ⇒ import 会失败）
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

STATE_LAYER_PATH = os.path.join(_ROOT, "creativity_lab", "state_layer.py")


# ══════════════════════════════════════════════════════════════
# ★ 五个测试（★ 断言要点 + 负向断言，★ 逐条对齐第二组的规格表）
# ══════════════════════════════════════════════════════════════

def test1_dead_end(SL):
    """★ **① 重复死路**：★ 同一方法连续 3 次无新信息 ⇒ `dead_end=True` ⇒ 记入 `progress`

    ★ 负向：① 持续有新信息 ⇒ 永不判死路 ② 死路状态下动作必须是 `switch_method`
    """
    st = SL.State(budget_remaining=10)

    # ── 正向：连续 3 次无新信息 ⇒ 死路 ──
    for _ in range(3):
        st = SL.record_attempt(st, "m1", produced_new=False)
    at = next(a for a in st.attempts if a.method == "m1")
    assert at.dead_end is True, "连续 3 次无新信息后 dead_end 应为 True，实际 %r" % (at.dead_end,)
    assert at.used == 3, "used 应累计为 3，实际 %r" % (at.used,)
    assert "dead_end:m1" in st.progress, "progress 应记录 dead_end:m1，实际 %r" % (st.progress,)

    # ── 负向①：持续有新信息 ⇒ 永不判死路 ──
    st2 = SL.State(budget_remaining=10)
    for _ in range(5):
        st2 = SL.record_attempt(st2, "m2", produced_new=True)
    at2 = next(a for a in st2.attempts if a.method == "m2")
    assert at2.dead_end is False, "持续有新信息时不得判死路，实际 %r" % (at2.dead_end,)
    assert not any(p.startswith("dead_end:") for p in st2.progress), \
        "持续有新信息时 progress 不得出现 dead_end，实际 %r" % (st2.progress,)

    # ── 负向②：死路状态下动作必须是 switch_method ──
    action, arg = SL.choose_action(st)
    assert action == "switch_method", "死路状态动作应为 switch_method，实际 %r" % (action,)
    assert arg == "m1", "switch_method 应指向死路方法名，实际 %r" % (arg,)

    # ── 负向③：★ 累计 ≠ 连续 ★（★ rev1 守门断言）──
    st3 = SL.State(budget_remaining=10)
    for ok in (True, True, False):        # 只有【最后】一次无新信息
        st3 = SL.record_attempt(st3, "m3", produced_new=ok)
    at3 = next(a for a in st3.attempts if a.method == "m3")
    assert at3.dead_end is False, \
        "★ (True,True,False) 只有 1 次连续无新信息 ⇒ 不得判死路，实际 dead_end=%r" % (at3.dead_end,)
    assert at3.used == 3, "used 仍应累计为 3，实际 %r" % (at3.used,)
    consec = getattr(at3, "consecutive_no_new", None)
    assert consec == 1, "consecutive_no_new 应为 1，实际 %r" % (consec,)

    # ── 负向④：有新信息 ⇒ 连续计数清零 ──
    st4 = SL.State(budget_remaining=10)
    for ok in (False, False, True):        # 中间有进展 ⇒ 连续计数应清零
        st4 = SL.record_attempt(st4, "m4", produced_new=ok)
    at4 = next(a for a in st4.attempts if a.method == "m4")
    assert at4.consecutive_no_new == 0, "有新信息后连续计数应清零，实际 %r" % (at4.consecutive_no_new,)
    assert at4.dead_end is False, "清零后不得判死路，实际 %r" % (at4.dead_end,)


def test2_refute_rollback(SL):
    """★ **② 反证触发回退**：★ 反证 ⇒ 假设转 `refuted` ⇒ 动作 `rollback` ⇒ 新增保留点 + 移动 `current_kp`

    ★ 负向：① 支持性证据不触发回退 ② 证据不许丢
    """
    st = SL.State(budget_remaining=10,
                  hypotheses=[SL.Hypothesis(hid="h1", statement="命题 H1")])

    # ── 正向：反证 ⇒ refuted ⇒ 动作 rollback ──
    st = SL.add_evidence(st, "h1", {"kind": "support", "text": "支持性材料"}, refutes=False)
    st = SL.add_evidence(st, "h1", {"kind": "counter", "text": "反证材料"}, refutes=True)
    h = st.hypotheses[0]
    assert h.status == SL.HYP_REFUTED, "反证后状态应为 refuted，实际 %r" % (h.status,)
    assert "refuted:h1" in st.progress, "progress 应记录 refuted:h1，实际 %r" % (st.progress,)
    action, arg = SL.choose_action(st)
    assert action == "rollback", "存在被反证假设时动作应为 rollback，实际 %r" % (action,)
    assert arg == "counter_evidence", "rollback 的理由应为 counter_evidence，实际 %r" % (arg,)

    # ── 保留点：新增 + current_kp 移动 ──
    n_keep_before = len(st.keep)
    kp_before = st.current_kp
    st2 = SL.rollback(st, "counter_evidence")
    assert len(st2.keep) == n_keep_before + 1, \
        "rollback 应新增一个保留点，之前 %d 之后 %d" % (n_keep_before, len(st2.keep))
    assert st2.current_kp != kp_before, \
        "rollback 应移动 current_kp，之前 %r 之后 %r" % (kp_before, st2.current_kp)
    assert st2.keep[-1].note == "counter_evidence", \
        "保留点应记录回退原因，实际 %r" % (st2.keep[-1].note,)
    assert "rollback:counter_evidence" in st2.progress, \
        "progress 应记录 rollback:counter_evidence，实际 %r" % (st2.progress,)

    # ── 负向①：支持性证据不触发回退 ──
    st3 = SL.State(budget_remaining=10,
                   hypotheses=[SL.Hypothesis(hid="h2", statement="命题 H2")])
    st3 = SL.add_evidence(st3, "h2", {"kind": "support", "text": "只是支持"}, refutes=False)
    assert st3.hypotheses[0].status == SL.HYP_OPEN, \
        "支持性证据后假设应仍为 open，实际 %r" % (st3.hypotheses[0].status,)
    action3, _ = SL.choose_action(st3)
    assert action3 != "rollback", "支持性证据不得触发 rollback，实际动作 %r" % (action3,)

    # ── 负向②：证据不许丢（★ 正证 + 反证都在）──
    assert len(h.evidence) == 2, "证据列表应保留 2 条，实际 %d" % (len(h.evidence),)
    kinds = sorted(e.get("kind") for e in h.evidence)
    assert kinds == ["counter", "support"], "证据内容应原样保留，实际 %r" % (kinds,)

    # ── ★ rev1 新增：支持性证据累积到阈值 ⇒ 转 supported ⇒ 不再阻塞 connect ──
    st4 = SL.State(budget_remaining=10,
                   hypotheses=[SL.Hypothesis(hid="h3", statement="命题 H3")])
    st4 = SL.add_evidence(st4, "h3", {"kind": "support", "text": "第一次支持"}, refutes=False)
    assert st4.hypotheses[0].status == SL.HYP_OPEN, \
        "★ 一次支持后假设应仍为 open（★ 一次可能是噪声），实际 %r" % (st4.hypotheses[0].status,)
    act4, _ = SL.choose_action(st4)
    assert act4 == "check_hypothesis", \
        "★ 一次支持后动作仍应是 check_hypothesis，实际 %r" % (act4,)
    st4 = SL.add_evidence(st4, "h3", {"kind": "support", "text": "第二次支持"}, refutes=False)
    assert st4.hypotheses[0].status == SL.HYP_SUPPORTED, \
        "★ 两次支持后假设应转 supported，实际 %r" % (st4.hypotheses[0].status,)
    assert "supported:h3" in st4.progress, \
        "progress 应记录 supported:h3，实际 %r" % (st4.progress,)
    assert any(p.startswith("evidence:h3:support:") for p in st4.progress), \
        "★ progress 应留支持性证据的痕，实际 %r" % (st4.progress,)
    st4 = SL.preserve_divergence(st4, {"id": "d1", "claim": "分歧"})
    act4b, _ = SL.choose_action(st4)
    assert act4b == "connect", \
        "★ 假设已被支持后不应再阻塞 connect，实际 %r" % (act4b,)


def test3_divergence(SL):
    """★ **③ 合法分歧保留**：★ 两条相反结论 ⇒ 两条都在 ⇒ 动作 `connect`

    ★ 负向：★ 分歧不得合并成一条（★ id 集合大小不变）
    """
    st = SL.State(budget_remaining=10)
    st = SL.preserve_divergence(st, {"id": "d1", "claim": "正结论", "side": "A"})
    st = SL.preserve_divergence(st, {"id": "d2", "claim": "相反结论", "side": "B"})

    assert len(st.divergences) == 2, "两条分歧都应保留，实际 %d" % (len(st.divergences),)
    ids = sorted(d.get("id") for d in st.divergences)
    assert ids == ["d1", "d2"], "分歧 id 集合应为 {d1,d2}，实际 %r" % (ids,)
    # ★ 用集合比较（★ 强度不变：两条都必须在且内容未被改写；★ 但不依赖中文码位序）
    claims = set(d.get("claim") for d in st.divergences)
    assert claims == set(["正结论", "相反结论"]), "相反结论都应原样保留，实际 %r" % (claims,)

    action, arg = SL.choose_action(st)
    assert action == "connect", "存在合法分歧时动作应为 connect，实际 %r" % (action,)
    assert arg == "divergence", "connect 的理由应为 divergence，实际 %r" % (arg,)

    # ── 负向：★ 不得合并成一条（★ 加第三条后 id 集合大小必须变 3）──
    st = SL.preserve_divergence(st, {"id": "d3", "claim": "第三条结论", "side": "C"})
    assert len(st.divergences) == 3, "分歧不得被合并，数量应随新增而增，实际 %d" % (len(st.divergences),)
    ids2 = sorted(d.get("id") for d in st.divergences)
    assert ids2 == ["d1", "d2", "d3"], "id 集合大小必须保持增长，实际 %r" % (ids2,)


def test4_subgoal_revocation(SL):
    """★ **④ 子目标撤销**：★ 撤销 ⇒ `revoked` + 原因记录 + `progress` 记录

    ★ 负向：① 撤销【不物理删除】（★ 历史长度不变）② 只影响被撤销的那一条（★ 兄弟目标仍 active）
    """
    st = SL.State(budget_remaining=10)
    st = SL.propose_subgoal(st, "s1", "子目标一")
    st = SL.propose_subgoal(st, "s2", "子目标二")
    assert len(st.subgoals) == 2, "初始应有两个子目标，实际 %d" % (len(st.subgoals),)

    st = SL.revoke_subgoal(st, "s1", "反馈不成立")

    # ── 正向：revoked + 原因 + progress ──
    g1 = next(g for g in st.subgoals if g.sid == "s1")
    assert g1.status == SL.SUBGOAL_REVOKED, "撤销后状态应为 revoked，实际 %r" % (g1.status,)
    assert g1.revocation_reason == "反馈不成立", \
        "撤销原因应被记录，实际 %r" % (g1.revocation_reason,)
    assert "revoke_subgoal:s1:反馈不成立" in st.progress, \
        "progress 应记录 revoke_subgoal:s1:反馈不成立，实际 %r" % (st.progress,)

    # ── 负向①：撤销【不物理删除】★ 历史长度不变 ──
    assert len(st.subgoals) == 2, "撤销不得物理删除子目标，长度应仍为 2，实际 %d" % (len(st.subgoals),)

    # ── 负向②：只影响被撤销的那一条 ★ 兄弟目标仍 active ──
    g2 = next(g for g in st.subgoals if g.sid == "s2")
    assert g2.status == SL.SUBGOAL_ACTIVE, "兄弟子目标应仍为 active，实际 %r" % (g2.status,)
    assert g2.revocation_reason == "", "兄弟子目标不应被写入撤销原因，实际 %r" % (g2.revocation_reason,)


def test5_budget_and_failure(SL):
    """★ **⑤ 预算用尽与失败调用**：★ 失败调用也扣预算；★ 失败进 `n_failed_calls`；
    ★ 归零 ⇒ `exhausted` ⇒ 动作 `stop`

    ★ 负向：① 失败不得把分母算小（★ `n_total == n_failed + 成功数`）② 耗尽后不因 open 假设而继续
    """
    st = SL.State(budget_remaining=1)

    st = SL.record_call(st, ok=False)
    assert st.n_calls_total == 1, "n_calls_total 应为 1，实际 %r" % (st.n_calls_total,)
    assert st.n_failed_calls == 1, "失败调用应记进 n_failed_calls，实际 %r" % (st.n_failed_calls,)
    assert st.budget_used == 1, "失败调用【也必须扣预算】，budget_used 应为 1，实际 %r" % (st.budget_used,)
    assert st.budget_remaining == 0, "budget_remaining 应归零，实际 %r" % (st.budget_remaining,)
    assert st.exhausted is True, "预算归零后 exhausted 应为 True，实际 %r" % (st.exhausted,)
    assert st.stop_reason == "budget_exhausted", \
        "stop_reason 应为 budget_exhausted，实际 %r" % (st.stop_reason,)
    action, _ = SL.choose_action(st)
    assert action == "stop", "预算耗尽后动作应为 stop，实际 %r" % (action,)

    # ── 负向①：★ 失败不得把分母算小 ──
    st2 = SL.State(budget_remaining=10)
    n_ok = 0
    n_bad = 0
    for i in range(6):
        ok = (i % 2 == 0)
        st2 = SL.record_call(st2, ok=ok)
        if ok:
            n_ok += 1
        else:
            n_bad += 1
    assert st2.n_calls_total == n_ok + n_bad, \
        "分母完整性被破坏：n_total=%r 而 成功 %d + 失败 %d" % (st2.n_calls_total, n_ok, n_bad)
    assert st2.n_failed_calls == n_bad, \
        "n_failed_calls 应等于失败次数 %d，实际 %r" % (n_bad, st2.n_failed_calls)

    # ── 负向②：★ 耗尽后不因 open 假设而继续 ──
    st3 = SL.State(budget_remaining=1,
                   hypotheses=[SL.Hypothesis(hid="h9", statement="仍未检验的假设")])
    st3 = SL.record_call(st3, ok=True)
    assert st3.exhausted is True, "预算耗尽后 exhausted 应为 True，实际 %r" % (st3.exhausted,)
    action3, _ = SL.choose_action(st3)
    assert action3 == "stop", \
        "预算耗尽后即便有 open 假设也必须 stop，实际 %r" % (action3,)


def test6_spec_redlines(SL):
    """★ **规格三条红线**（★ 第二组原文写死的 ⇒ ★ 规格的一部分）：

    ★ ① 状态是【可序列化的纯数据】⇒ ⇒ JSON 可序列化
    ★ ② 更新规则是【纯函数】（★ 旧状态 → 新状态，★ 不就地改）⇒ ⇒ 原状态不被改
    """
    # ── 红线①：可序列化 ──
    st = SL.State(budget_remaining=3)
    st = SL.propose_subgoal(st, "s1", "子目标一")
    st = SL.add_evidence(st, "h1", {"kind": "counter"}, refutes=True)
    st = SL.preserve_divergence(st, {"id": "d1", "claim": "c"})
    st = SL.record_call(st, ok=True)
    try:
        blob = json.dumps(st.to_dict(), ensure_ascii=False)
    except Exception as e:  # pragma: no cover
        raise AssertionError("状态必须可 JSON 序列化，但抛了 %s: %s" % (type(e).__name__, e))
    assert len(blob) > 0, "序列化结果不应为空"

    # ── 红线②：纯函数 ⇒ 旧状态不被就地修改 ──
    st_old = SL.State(budget_remaining=5)
    snapshot = json.dumps(st_old.to_dict(), ensure_ascii=False, sort_keys=True)
    st_new = SL.record_call(st_old, ok=False)
    after = json.dumps(st_old.to_dict(), ensure_ascii=False, sort_keys=True)
    assert snapshot == after, "更新规则必须不就地改旧状态（★ 纯函数）"
    assert st_new is not st_old, "更新规则必须返回新对象"
    assert st_new.n_calls_total == 1 and st_old.n_calls_total == 0, \
        "新旧状态应互不影响：新 %r / 旧 %r" % (st_new.n_calls_total, st_old.n_calls_total)


def test7_detect_tie(SL):
    """★ **⑦ 并列检测（rev3）**：★ 返回【所有】并列簇（★ `List[Dict]`）；★ 无并列 ⇒ `[]`

    ★ 负向：★ **`detect_tie` 不改状态**（★ 纯函数 ⇒ 接线方式由调用方决定）
    ★ ★ 第二组裁决：「并列 ⇒ 分歧」是【规则的一部分】⇒ ⇒ 接口层提供能力，★ 接线归第四组

    ★ ★★ rev3 相对 rev2 的变化（★ 2026-10-25 第二组落地）★★：
    ★ ★ ① `tol` 从【死参数】变成【必填关键字参数】（★ keyword-only、★ 无默认值）
    ★ ★ ② 分组规则从 `round(v, 12)` 改成【排序后相邻差 ≤ tol】（★ 传递闭包）
    ★ ★ ③ 返回类型 / 簇序 / members·scores 结构【不变】⇒ ⇒ 第四组探针【不用改】
    """

    # ══ rev2 时代的语义（★ 必须继续成立）══
    # ── 无并列 ⇒ 空列表（★ rev2 起：不是 None）──
    assert SL.detect_tie([0.1, 0.5, 0.9], tol=1e-9) == [], "无并列时应返回空列表"
    assert SL.detect_tie([], tol=1e-9) == [], "空列表应返回空列表"
    assert SL.detect_tie([0.5], tol=1e-9) == [], "单元素应返回空列表（无并列可言）"

    # ── 有并列 ⇒ 返回 members ──
    tie = SL.detect_tie([0.9, 0.9, 0.2], tol=1e-9)
    assert tie is not None and len(tie) >= 1, "有两个 0.9 时应检出并列"
    clusters = tie if isinstance(tie, list) else [tie]
    first = clusters[0]
    assert first.get("kind") == "tie", "kind 应为 tie，实际 %r" % (first.get("kind"),)
    assert sorted(first.get("members") or []) == [0, 1], \
        "members 应为 [0,1]，实际 %r" % (first.get("members"),)
    assert sorted(first.get("scores") or []) == [0.9, 0.9], \
        "scores 应为并列两者的分数，实际 %r" % (first.get("scores"),)

    # ── 三个并列 ──
    tie3 = SL.detect_tie([0.5, 0.5, 0.5], tol=1e-9)
    assert tie3 is not None and len(tie3) >= 1, "三个并列应检出并列"
    clusters3 = tie3 if isinstance(tie3, list) else [tie3]
    assert len(clusters3[0].get("members") or []) == 3, \
        "三个并列应检出 3 个成员，实际 %r" % (clusters3[0].get("members"),)

    # ── ★★ 中位并列【也必须检出】（★ rev2 修的第 5 条差异）★★
    mid = SL.detect_tie([0.9, 0.5, 0.5], tol=1e-9)
    assert mid is not None and len(mid) >= 1, \
        "★★ 中位并列（0.5,0.5）也是合法分歧 ⇒ 必须检出，实际 %r" % (mid,)
    mid_clusters = mid if isinstance(mid, list) else [mid]
    members = set()
    for c in mid_clusters:
        members.update(c.get("members") or [])
    assert {1, 2} <= members, \
        "★★ 中位并列成员 {1,2} 应被检出，实际 %r" % (members,)

    # ── 负向：★ 不改状态（★ 纯函数）──
    st = SL.State(budget_remaining=5)
    before = json.dumps(st.to_dict(), ensure_ascii=False, sort_keys=True)
    SL.detect_tie([0.9, 0.5, 0.5], tol=1e-9)
    after = json.dumps(st.to_dict(), ensure_ascii=False, sort_keys=True)
    assert before == after, "★ detect_tie 是纯函数 ⇒ 不得修改状态"

    # ── ★ 接线语义：检出并列 ⇒ 调用方可写入分歧 ⇒ 动作变 connect ──
    st2 = SL.State(budget_remaining=5)
    for d in (SL.detect_tie([0.9, 0.9, 0.2], tol=1e-9) or []):
        st2 = SL.preserve_divergence(st2, d)
    act, arg = SL.choose_action(st2)
    assert act == "connect", "写入分歧后动作应为 connect，实际 %r" % (act,)

    # ══════════════════════════════════════════════════════════════
    # ★★★ rev3 专属断言（★ 每条都必须是【只有 rev3 才通过】）★★★
    # ══════════════════════════════════════════════════════════════

    # ★ rev3 ① 差 1e-10（≤ tol=1e-9）⇒ 判并列
    #   ★ ★ 独立实现：★ 用 [0.3, 0.3+1e-10]（★ 不用第二组那组输入值）
    t1 = SL.detect_tie([0.3, 0.3 + 1e-10], tol=1e-9)
    assert len(t1) == 1, "★ rev3①：差 1e-10 ≤ tol ⇒ 应有 1 簇，实际 %r" % (t1,)
    assert t1[0].get("members") == [0, 1], \
        "★ rev3①：members 应为 [0,1]，实际 %r" % (t1[0].get("members"),)

    # ★ rev3 ② 同一对分值、tol=1e-11 ⇒ 【不】并列（★ 证明 tol 真的在起作用，★ 不是死参数）
    t2 = SL.detect_tie([0.3, 0.3 + 1e-10], tol=1e-11)
    assert t2 == [], "★ rev3②：tol=1e-11 ⇒ 差 1e-10 > tol ⇒ 不该并列，实际 %r" % (t2,)

    # ★ rev3 ③ 传递闭包：三值相邻差都 ≤ tol ⇒ 归一簇
    t3 = SL.detect_tie([0.5, 0.5 + 0.4e-9, 0.5 + 0.8e-9], tol=1e-9)
    assert len(t3) == 1, "★ rev3③：传递闭包 ⇒ 应归一簇，实际 %r" % (t3,)
    assert t3[0].get("members") == [0, 1, 2], \
        "★ rev3③：members 应为 [0,1,2]，实际 %r" % (t3[0].get("members"),)

    # ★ rev3 ④ ★★ 簇内【首尾差 1.8e-9 > tol】⇒ 仍归一簇（★ ⇒ tol ≠ 簇内最大跨度）
    t4 = SL.detect_tie([0.5, 0.5 + 0.9e-9, 0.5 + 1.8e-9], tol=1e-9)
    assert len(t4) == 1, "★ rev3④：首尾差 1.8e-9 > tol 仍应归一簇，实际 %r" % (t4,)
    sc4 = t4[0].get("scores") or []
    assert sc4 and abs((max(sc4) - min(sc4)) - 1.8e-9) < 1e-15, \
        "★ rev3④：簇内首尾差应约 1.8e-9（★ > tol），实际 %r" % (sc4,)

    # ★ rev3 ⑤ ★★ 不传 tol ⇒ TypeError（★ 必填 ⇒ 漏传【立刻炸】而不是静默用默认值）
    try:
        SL.detect_tie([0.5, 0.5])
        raise AssertionError("★ rev3⑤：不传 tol 应当 TypeError（★ tol 是必填关键字参数）")
    except TypeError:
        pass

    # ★ rev3 ⑥ ★★ 位置传 tol ⇒ TypeError（★ keyword-only ⇒ 逼调用方显式写 tol=）
    try:
        SL.detect_tie([0.5, 0.5], 1e-9)
        raise AssertionError("★ rev3⑥：位置传 tol 应当 TypeError（★ keyword-only）")
    except TypeError:
        pass

    # ★ rev3 ⑦ ★★ 与 rev2 的【真实差异点】：★ tol=1e-13、差 5e-13 ⇒ 【不】并列
    #   ★ rev2（round(v,12)）会判为并列 ⇒ ⇒ ★ 这条是【rev2 挂、rev3 过】的断言
    t7 = SL.detect_tie([0.7, 0.7 + 5e-13], tol=1e-13)
    assert t7 == [], "★ rev3⑦：tol=1e-13、差 5e-13 ⇒ 不该并列（★ rev2 会并列），实际 %r" % (t7,)

    # ★ rev3 ⑧ ★★ members 必须是【原索引升序】（★ 簇内按分值降序会破坏它）
    #   ★ ★ 第二组 rev3 初版曾把 members 改成"按分值降序"⇒ ⇒ ★ ★ 这条守住"原索引升序"
    t8 = SL.detect_tie([0.7, 0.2, 0.7], tol=1e-9)
    assert len(t8) == 1, "★ rev3⑧：应有 1 簇，实际 %r" % (t8,)
    assert t8[0].get("members") == [0, 2], \
        "★ rev3⑧：members 应按【原索引升序】= [0,2]，实际 %r" % (t8[0].get("members"),)
    sc8 = t8[0].get("scores") or []
    assert sc8 and abs(sc8[0] - 0.7) < 1e-12 and abs(sc8[1] - 0.7) < 1e-12, \
        "★ rev3⑧：scores 应与 members 同序（★ 两者都是 0.7），实际 %r" % (sc8,)


def test8_rev1_regressions(SL):
    """★ **⑧ rev1 三个真 bug 的回归（★ 第二组出断言规格 / 第四组实现）**

    ★ ★ 这组测试存在的理由 = ★ 「离线全绿 ≠ 语义无歧义」：
    ★ 旧实现的「累计」语义与规格的「连续」语义**都能通过旧测试** ⇒ ⇒ 旧测试抓不住 bug ②
    ★ ⇒ ⇒ ★ **每修一个 bug，必须补一条【只有新实现才通过】的断言**
    """
    # ── ① HYP_SUPPORTED 可达 + connect 不再被阻塞 ──
    st = SL.State(budget_remaining=10,
                  hypotheses=[SL.Hypothesis(hid="h1", statement="命题")])
    act, _ = SL.choose_action(st)
    assert act == "check_hypothesis", "★ 支持前动作应为 check_hypothesis，实际 %r" % (act,)
    st = SL.add_evidence(st, "h1", {"kind": "support"}, refutes=False)
    assert st.hypotheses[0].status == SL.HYP_OPEN, "★ 一次支持后仍应 open，实际 %r" % (st.hypotheses[0].status,)
    st = SL.add_evidence(st, "h1", {"kind": "support"}, refutes=False)
    assert st.hypotheses[0].status == SL.HYP_SUPPORTED, \
        "★ 两次支持后应转 supported，实际 %r" % (st.hypotheses[0].status,)
    st = SL.preserve_divergence(st, {"id": "d1", "claim": "c"})
    act, _ = SL.choose_action(st)
    assert act == "connect", "★ 支持后不应再阻塞 connect，实际 %r" % (act,)

    # ── ② 死路判定看【连续】不看【累计】──
    st2 = SL.State(budget_remaining=10)
    for ok in (True, True, False):
        st2 = SL.record_attempt(st2, "m", produced_new=ok)
    a = next(x for x in st2.attempts if x.method == "m")
    assert a.dead_end is False, "★ (True,True,False) 不得判死路，实际 %r" % (a.dead_end,)
    assert a.used == 3 and a.consecutive_no_new == 1, \
        "★ used=3 且 consecutive_no_new=1，实际 used=%r consec=%r" % (a.used, a.consecutive_no_new)

    st3 = SL.State(budget_remaining=10)
    for _ in range(3):
        st3 = SL.record_attempt(st3, "m2", produced_new=False)
    a2 = next(x for x in st3.attempts if x.method == "m2")
    assert a2.dead_end is True, "★ 连续 3 次无新信息应判死路，实际 %r" % (a2.dead_end,)

    st4 = SL.State(budget_remaining=10)
    for ok in (False, False, True):
        st4 = SL.record_attempt(st4, "m3", produced_new=ok)
    a3 = next(x for x in st4.attempts if x.method == "m3")
    assert a3.consecutive_no_new == 0, "★ 有新信息应清零连续计数，实际 %r" % (a3.consecutive_no_new,)

    # ── ③ 支持性证据留痕（★ 可回放）──
    st5 = SL.State(budget_remaining=10,
                   hypotheses=[SL.Hypothesis(hid="h9", statement="命题")])
    st5 = SL.add_evidence(st5, "h9", {"kind": "support"}, refutes=False)
    assert any(p.startswith("evidence:h9:support:") for p in st5.progress), \
        "★ progress 应留支持证据痕，实际 %r" % (st5.progress,)


# ══════════════════════════════════════════════════════════════
# 测试套件驱动
# ══════════════════════════════════════════════════════════════

TESTS = [
    ("test1_dead_end", test1_dead_end),
    ("test2_refute_rollback", test2_refute_rollback),
    ("test3_divergence", test3_divergence),
    ("test4_subgoal_revocation", test4_subgoal_revocation),
    ("test5_budget_and_failure", test5_budget_and_failure),
    ("test6_spec_redlines", test6_spec_redlines),
    ("test7_detect_tie", test7_detect_tie),
    ("test8_rev1_regressions", test8_rev1_regressions),
]


def run_suite(SL, only=None):
    """★ 跑测试套件 ⇒ 返回 [(name, ok, msg)]；★ 失败项必须显式（★ 不许静默通过）"""
    results = []
    for name, fn in TESTS:
        if only is not None and name != only:
            continue
        try:
            fn(SL)
            results.append((name, True, ""))
        except AssertionError as e:
            results.append((name, False, "AssertionError: %s" % (e,)))
        except Exception as e:
            results.append((name, False, "%s: %s" % (type(e).__name__, e)))
    return results


def _load_real():
    return importlib.import_module("creativity_lab.state_layer")


def _load_mutant(tmpdir, name, old, new):
    """★ 造一个【规则变异体】⇒ ⇒ 用它跑测试 ⇒ ⇒ 测试【必须失败】（★ 否则测试是假绿）"""
    with open(STATE_LAYER_PATH, "r", encoding="utf-8") as f:
        src = f.read()
    if old not in src:
        raise AssertionError("变异锚点不存在（★ 说明原文已变 ⇒ 变异注入失效）：%r" % (old,))
    mutated = src.replace(old, new, 1)
    path = os.path.join(tmpdir, name + ".py")
    with open(path, "w", encoding="utf-8") as f:
        f.write(mutated)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    # ★ 必须先注册进 sys.modules ⇒ ⇒ dataclass 解析 `from __future__ import annotations`
    # ★ 带来的字符串注解时，要查 `sys.modules[cls.__module__].__dict__` ⇒ 没注册就是 None ⇒ 崩。
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ★ 变异清单：★ 每个变异对应【必须抓到它的那一项测试】
MUTATIONS = [
    ("m1_deadend_threshold",
     "    if at.consecutive_no_new >= DEAD_END_THRESHOLD:",
     "    if at.consecutive_no_new >= 99:",
     "test1_dead_end",
     "★ 死路阈值被改宽（3→99）"),
    ("m2_no_budget_charge",
     "s.budget_remaining = max(0, s.budget_remaining - 1)",
     "s.budget_remaining = s.budget_remaining",
     "test5_budget_and_failure",
     "失败/成功调用都不再扣预算"),
    ("m3_physical_delete",
     "            g.status = SUBGOAL_REVOKED\n            g.revocation_reason = reason\n",
     "            s.subgoals.remove(g)\n            return s\n",
     "test4_subgoal_revocation",
     "撤销变成物理删除（★ 违反『不得物理删除』）"),
    ("m4_no_connect",
     '    if st.divergences:\n        return "connect", "divergence"\n',
     '    if st.divergences:\n        return "explore", "divergence"\n',
     "test3_divergence",
     "分歧不再触发 connect"),
    ("m5_fail_not_counted",
     "        s.n_failed_calls += 1",
     "        pass",
     "test5_budget_and_failure",
     "失败调用不再计入分母（★ 静默归零）"),
    ("m6_no_rollback_priority",
     "    if any(h.status == HYP_REFUTED for h in st.hypotheses):",
     "    if False:",
     "test2_refute_rollback",
     "反证不再优先触发回退"),
    # ── ★ rev1 三条新语义的守门变异（★ 证明新断言是活的）──
    ("m7_back_to_cumulative",
     "    if at.consecutive_no_new >= DEAD_END_THRESHOLD:",
     "    if not produced_new and at.used >= DEAD_END_THRESHOLD:",
     "test1_dead_end",
     "★ 死路判定退回【累计】语义（★ 旧 bug 复活）"),
    ("m8_no_supported_path",
     "                if n_sup >= SUPPORT_THRESHOLD and h.status == HYP_OPEN:",
     "                if False:",
     "test8_rev1_regressions",
     "★ 支持性证据不再转 supported（★ 旧 bug ① 复活 ⇒ connect 重新被阻塞）"),
    ("m9_no_support_trace",
     '                s.progress.append("evidence:%s:support:%d" % (hid, n_sup))',
     "                pass",
     "test8_rev1_regressions",
     "★ 支持性证据不留痕（★ 旧 bug ③ 复活）"),
    # ★ ★ rev3 专属变异（★ 2026-10-25 第二组落地 rev3 后加）★ ★
    ("m10_detect_tie_tol_ignored",
     "    if float(scores[i]) - float(scores[cur[-1]]) <= tol:",
     "    if float(scores[i]) - float(scores[cur[-1]]) <= 1e9:",
     "test7_detect_tie",
     "★★ detect_tie 的 tol 失效（★ ★ 什么都合一簇 ⇒ rev3②⑦ 必挂）★★"),
    ("m12_detect_tie_tol_optional",
     "def detect_tie(scores: List[float], *, tol: float) -> List[Dict[str, Any]]:",
     "def detect_tie(scores: List[float], tol: float = 1e-9) -> List[Dict[str, Any]]:",
     "test7_detect_tie",
     "★★ tol 变回可选且有默认值（★ ★ 漏传不再 TypeError ⇒ rev3⑤⑥ 必挂）★★"),
    ("m13_detect_tie_members_by_score_desc",
     "        g_asc = sorted(g)",
     "        g_asc = sorted(g, key=lambda i: -float(scores[i]))",
     "test7_detect_tie",
     "★★ members 改成按分值降序（★ ★ 违反『原索引升序』⇒ rev3⑧ 必挂）★★"),
    ("m14_detect_tie_not_transitive",
     "    if float(scores[i]) - float(scores[cur[-1]]) <= tol:",
     "    if float(scores[i]) - float(scores[cur[0]]) <= tol:",
     "test7_detect_tie",
     "★★ 分组改成与簇【首】比较（★ ★ 非传递 ⇒ rev3④ 必挂）★★"),
    ("m11_detect_tie_always_none",
     "    return out",
     "    return []",
     "test7_detect_tie",
     "★ detect_tie 永远返回空列表（★ 并列检测完全失效）"),
]


def self_test():
    """★ **变异注入自检** ⇒ ⇒ 每个测试项都必须证明【自己抓得住东西】"""
    print("=== ★ 变异注入自检（★ 证明测试是活的，不是假绿）===")
    ok_all = True
    tmpdir = tempfile.mkdtemp(prefix="state_layer_mut_")
    try:
        for mut_name, old, new, target_test, why in MUTATIONS:
            try:
                mod = _load_mutant(tmpdir, mut_name, old, new)
            except Exception as e:
                print("  ✘ %-24s ★ 变异体构造失败 ⇒ %s: %s" % (mut_name, type(e).__name__, e))
                ok_all = False
                continue
            res = run_suite(mod, only=target_test)
            if not res:
                print("  ✘ %-24s ★ 目标测试 %s 不存在" % (mut_name, target_test))
                ok_all = False
                continue
            name, ok, msg = res[0]
            if ok:
                print("  ✘ %-24s ★ **假绿** ⇒ 变异后 %s 仍然通过（★ 该测试抓不住：%s）"
                      % (mut_name, target_test, why))
                ok_all = False
            else:
                print("  ✔ %-24s ⇒ %s 如期失败：%s" % (mut_name, target_test, msg[:110]))
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)
    if ok_all:
        print("=== ★ 变异注入自检：%d/%d 项全部如期失败 ⇒ 测试是活的 ===" % (len(MUTATIONS), len(MUTATIONS)))
    return 0 if ok_all else 1


def main(argv):
    mode = argv[1] if len(argv) > 1 else "run"
    if mode == "--self-test":
        return self_test()

    SL = _load_real()
    print("=== ★ 状态层规格离线测试（★ 第二组出规格 / 第四组实现测试）===")
    print("★ 模块：%s" % (STATE_LAYER_PATH,))
    print("★ 接口归属：第二组（★ 实现与读数归第四组）")
    results = run_suite(SL)
    n_ok = 0
    for name, ok, msg in results:
        if ok:
            n_ok += 1
            print("  ✔ %s" % (name,))
        else:
            print("  ✘ %s ⇒ %s" % (name, msg))
    total = len(results)
    print("=== ★ 结果：%d/%d 通过 ===" % (n_ok, total))
    if n_ok != total:
        print("=== ★ 有失败项 ⇒ exit 1 ===")
        return 1
    print("=== ★ 全部通过 ⇒ exit 0 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
