---
name: state-driven-agent
description: 当需要让 Agent「由内部状态决定下一步行为」时使用（状态机、决策留痕、可回滚推理、证据驱动推进、Agent 自我约束、多轮长任务）。提供可复用的状态机内核（State/subgoal/evidence/rollback/tie-detect）与"状态必须进生成过程内部"的判死门。触发词：状态机、状态驱动、内部状态、决策留痕、回滚、证据、Agent 架构、状态绑定、承诺兑现。不要用于：单轮问答（状态层是纯开销）。
---

# 状态机 · 状态驱动 Agent

> 来自「层 4：Agent 的状态驱动」这条研究线的**可执行结论 + 可复用内核**。

## 核心结论（★ 强度已校准）

> **当前形态的状态机未被证明优于等强度提示词** —— ★ 这是**边界结论**，不是"状态驱动无效"。
> ⇒ 但★ **反馈通路成立且强分离**：D2 换初稿 **0.0176** vs D0 纯重跑地板 **0.1606** ⇒ **分离比 9.13×**（状态历史确实主导产出内容构成）。
> ⇒ ★ **驱动力通路在几何读数上归零**：D0 0.0720 / D2' 换决策 0.1077 / D3 换无关缺口 0.0934；预注册判据（逐例更低 ≥2/3 且 均值比 ≤0.70）**三条全否**。
> ⇒ ★ **决策翻成"放弃"，相关实体一个都没消失**（base 11/12=0.917 ｜ D2' **12/12=1.000** ｜ D0 5/12=0.417）⇒ **"取舍"没在产出里兑现**。
> ⇒ ⇒ ★ **两条通路必须分开判**（反馈 ≠ 驱动力）。

★ **换判官读数方向相反**（两两比较 A vs WF-a3，D1 取舍明确度 3 胜 15 负，位置一致率 0.889）⇒ ★ **几何读数与判官读数都要报，矛盾本身就是结论。**

## 核心洞见（★ 这条决定了 skill 的形态）

> ★ **状态必须在【生成过程内部】起作用，否则只是装饰。**
> ⇒ 一个"状态层"如果只在外围记录/汇总，等于没接上。
> ⇒ ⇒ **因此本 skill 提供的是可插入生成循环的状态机内核，而不是一份"建议用状态机"的文章。**

## 内核 API

```python
from state_layer import (
    State, propose_subgoal, revoke_subgoal, revise_subgoal,
    add_evidence, rollback, record_attempt, record_call, detect_tie,
)

st = State()
st = propose_subgoal(st, "s1", "先验证是否存在唯一推导")
st = add_evidence(st, "h1", {"kind": "probe", "result": "1 path"})
st = record_attempt(st, method="derive", produced_new=True)
st = record_call(st, ok=True)
st = detect_tie(scores, tol=0.01)      # 平局检测
st = rollback(st, reason="证据反证")
```

★ **实测状态（2026-10-24）**：`propose_subgoal` / `record_attempt` / `record_call` / `detect_tie` / `rollback` 均已验证可跑（`test_state_layer.py` **8/8 通过，exit 0**，含变异注入）。
★ ⚠️ **`add_evidence` 的 `ev` 字段契约未核清** —— 本机实测调用后 `st.hypotheses` 仍为 `[]` ⇒ ★ **用前先回源 `creativity_lab/state_layer.py` 核 `ev` 的字段结构**，不要假设它一定写入。
★ `State` 公开字段：`attempts · budget_remaining · budget_used · current_kp · divergences · exhausted · hypotheses · keep · n_calls_total · n_failed_calls · progress · stop_reason · subgoals`

★ `State` 含 `Hypothesis` / `Subgoal` / `Attempt` / `KeepPoint`；`clone()` 支持快照与分叉。
★ `apply_state_layer_rev3.py` 是把它接进 agent 循环的现成实现（v1→v4 演进版）。

## 判死门：★ C1 vs C0（硬约束）

★ **所有离散结构量判据必须报 C1 vs C0**（C1 = 有状态层，C0 = 无状态层等预算对照）—— ⇒ **不做 C1 vs C0 的读数，不能用来支持"状态有用"**。
★ 扩样规格已写全：**n ≈ 20 配对 = 10 题 × 4 样本**。

## 下一代的结构化绑定（v5 方案，已定版未实现）

★ 状态以**结构化绑定**留在产出里 ⇒ 候选**显式声明**"这一轮写透了 A、放弃了 B" ⇒ 打分改为**读这个声明 + 核验兑现**：
★ **声明放弃 B 但正文写了 B ⇒ 算违禁。**
⇒ ⇒ ★ 这把"驱动力"从**不可观测**变成**可核验的兑现率** ⇒ ★ 也把"状态里的取舍有没有真的落到文字上"变成一个可自动检查的量。

## 硬纪律

1. ★ **反馈通路 ≠ 驱动力通路** —— 分开判，别混着报。
2. ★ **C1 vs C0 是硬约束**。
3. ★ **几何读数与判官读数都报**；矛盾不取舍。
4. ★ **判官先过位置去偏**（位置一致率 <0.5 ⇒ 该对比判不可用）；绝对打分有天花板效应 ⇒ 只用题内相对排序、不可跨判官比。
5. ★ **v5 的兑现率核验要真跑**（声明与正文的一致性检查）—— ★ v3 的教训是：v5 兑现率 0.528 / 违禁率 0.333 ⇒ **状态里没有代价就无所谓驱动力**。

## 健康领域安全门（★ 若任务涉及 ADHD 机制）

★ 本 skill 源自 ADHD 认知机制研究 ⇒ ★ **不做诊断**，不评估任何人是否符合 ADHD（**包括说话者自己**），不给药物/剂量/停药/加药建议 ⇒ 一律转向专业医生。★ 这条不是免责文字，是写进 skill 的拦截门。

## 参考

`scripts/`：`state_layer.py`（内核）、`apply_state_layer_rev3.py`（接入 agent 循环）、`test_state_layer.py` + `test_state_layer_rev3_mutations.py`（★ 含变异注入测试）、`probe_select_boundary.py`、`probe_state_layer_spec_gap.py`、`check_independent_samples.py`
`references/`：`ADHD-trait-to-agent.md`（ADHD 特质→Agent 实现路径）、`experiment-report-4q.md`
