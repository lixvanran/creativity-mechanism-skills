---
name: learning-route-generalization
description: 当需要「从经验中学习/自迭代/训练一个策略」并评估其效果时使用（自迭代优化、策略学习、few-shot 记忆、轨迹学习、agent 自我改进）。核心是判死门设计：训练集内分离 ≠ 泛化，必须用留出集 + 预注册 + 可检出力地板来判。触发词：学习、训练、自迭代、自我改进、策略学习、留出集、泛化、过拟合、few-shot、记忆积累、评估效果。不要用于：单次推理质量优化（那是设计路线）。
---

# 学习路线 · 泛化判死门

> 来自「层 3：运用训练/自迭代的手段优化搜索空间塌缩」这条研究线的**可执行结论**。
> ★ 这条线的核心贡献不是"我们学到了什么"，而是「**训练内分离 + 留出无分离 = 训练无留出集的代价第一次被数据记下**」。

## 核心结论（★ 强度已校准）

> 机制主张若成立，**拆掉它应当改善**。⇒ 训练集内出现分离、**留出集上无分离** ⇒ ⇒ **泛化未被证明**（≠ "已证明无泛化"）。
> ⇒ ⇒ **训练无留出集的代价，第一次被数据记下来了。**

★ 留出集读数（3 策略 × 8 rep）：负对照臂各 8（merged13 4/8、lookup 5/8、uniform 5/8）⇒ **判平，可读 W 臂**；W 臂 2/8 · 3/8 · 2/8，承重维度中位 2.00 / 2.50 / 2.00 ⇒ **三条均不可分辨**。检出力地板 **0.51 SE / 0.54 SE**。
★ in-sample 2/6 · 4/6 · 5/6 有分离 ⇒ **留出无分离** ⇒ 这对组合就是完整判死门形态。

## 怎么用

### 1. 先写预注册（★ 在跑批之前，不是在跑完之后）

`references/PREREG-HOLDOUT-2026-10-24.md`（留出集）、`PREREG-DECISION-RULES-2026-10-22.md`（判决规则）、`PREREG-FRAME-SWEEP-2026-10-25.md`（frame 扫描）、`PROTOCOL.md`、`DEV-SPEC.md`（题集规格）—— ★ **直接可改用**。

★ 预注册必须写死：分析单元=题 · 题内配对 · 哪些算"过" · 哪些算"不过" · 尚不能判的部分。

### 2. 主读数：`n_dims`（有效信息维度数）

```python
from space import path_diversity, ops_entropy, frame_coverage, space_report
from metrics_priorart import majority_share, distinct_families, dse, self_sim, ess, marginal_util
```

★ **主读数是 `n_dims`，不是 `n_load_bearing`** —— ★ 这是回源 `finish_table.sh` 才发现的：既有表里标"承重维度中位"的那一列**实际取的是 `n_dims`**。⇒ **两表不可混引。**

★ `metrics_priorart.py` 的指标全部**有出处**（不是自造）：`majority_share`/`distinct_families`/`dse` ← Self-Consistency (ICLR'23) / Kuhn et al. (arXiv:2302.09664)；`ess` ← ePF (arXiv:2510.05825)；`self_sim`/`collision_ratio` ← Lake et al. (NAACL'25, arXiv:2406.17692) / Skobelev et al. (arXiv:2609.16454)。

### 3. 负对照必须先判读（★ 否则不许出优劣结论）

★ 实测：**负对照不平**（direct vs bestof3 的 `n_dims` 中位最大差 = 1.00）⇒ ⇒ 按预注册：**只报读数 + 噪声地板，不报架构优劣**。
★ 差值/合并σ：12 个（策略×题×对照）对比中 **Δ ÷ 合并σ ≥ 1.0 的 7 个、< 1.0 的 5 个**；最分离 3.42σ、最弱 0.00σ。★ **"分离"只表示统计上可分辨，不表示"更好"。**

### 4. 检出力地板（★ 报"不可分辨"必须同时报）

```python
from nested_calib_self import nested_calib_self
from analyze_batch import analyze_batch
```

★ H0 零分布的**唯一合法来源：同臂、同题、不同 rep**（rep 差异是纯噪声 ⇒ 天然零分布）⇒ **rep ≥ 2 是标定的最低要求**。
★ 门槛 θ₀ 锚在**本批自己的噪声地板**，**不许拿文献阈值当判决线**。
★ ★ **θ₀ 以题内 rep σ 为单位**（如 θ₀ = 1.33 σ）⇒ 引用时必须写「≥ θ₀ 个题内 rep σ」——**否则会被误读成绝对阈值**。

### 5. 独立复核（★ 别只信自己）

```bash
python3 scripts/family_recompute.py      # 从原始输出独立重算
python3 scripts/condition_clause_scan.py # 条件从句扫描（措辞越权检查）
python3 scripts/judge_agreement.py       # 判官一致率
```

## 硬纪律

1. ★ **行数 ≠ 有效分母** —— 失败单元不计 0、不进分母、每表显式报数，每格写「有效(原始)」。
2. ★ **不可分辨 ≠ 无效应 ≠ 两者等价**。
3. ★ **零分辨力尺子先剔除再参与一致性门** —— 否则它能**否决**一个真的一致（假阴性方向更危险）。
4. ★ **同一批样本产生的多条平读数不独立** —— 不得当成多个独立阴性证据重复计数。
5. ★ **事后重算必须标注** —— 且修正的必要性必须**不依赖结果方向**。
6. ★ **负对照未判读前不许改稿**（"留出未复现"这类措辞 = 拿半批数据下结论）。

## 参考

`references/`：5 份预注册与题集规格 ｜ `scripts/`：`space.py`（零判官空间度量）、`metrics_priorart.py`（前人口径对齐）、`nested_calib_self.py`（嵌套子集校准）、`analyze_batch.py`、`auto_validate.py`、`merge_policies.py`、三个独立复核脚本
