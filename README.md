# Creativity Mechanism Skills

**三份从「LLM Agent 搜索空间塌缩」研究中长出来的可执行 Agent Skill。**
MIT License ｜ 2026-10

> 每个 skill 不是"通用建议"，而是**某条研究线的判决 + 可运行代码 + 预注册**三件套。
> **判决的强度就是它被实测支撑的强度** —— 边界结论写成边界结论，不夸大。

---

## 三个 skill

| Skill | 来自 | 回答什么 | 核心结论（窄表述） |
|---|---|---|---|
| [`design-route-space-expansion`](skills/design-route-space-expansion/) | 层 2 · 设计路线 | 怎么**拓宽**搜索空间、避免答案同质化 | 杠杆是【交互结构 × 任务结构】的交互，**二者必须分开测**；prompt 级身份多样性无效 |
| [`learning-route-generalization`](skills/learning-route-generalization/) | 层 3 · 学习路线 | 怎么判断"从经验里学到的"是**真泛化**还是过拟合 | 训练内分离 + 留出无分离 ⇒ **泛化未被证明**；训练无留出集的代价第一次被数据记下 |
| [`state-driven-agent`](skills/state-driven-agent/) | 层 4 · 状态机 | 怎么让 Agent **由内部状态决定下一步行为** | 当前形态状态机**未被证明优于**等强度提示词（边界结论）；但反馈通路成立（9.13× 分离）⇒ **两条通路必须分开判** |

★ **层 1（问题描述与原因 · 注意力机制）不在这三份里** —— 它是**理论层**，本项目内 logits/logprobs 不可得、无 GPU ⇒ 归因到注意力机制**不成立** ⇒ ⇒ 只能写「与注意力机制相容，但本文未检验该假设」⇒ ⇒ **不做成 skill，因为 skill 会暗示"有办法"**。

---

## 为什么这三个 skill 的写法值得抄

★ 每份 SKILL.md 里都有三样别处少见的东西：

1. **★ 结论写成"能支撑的强度"，不是"想说的强度"**
   例如层 2 的结论不是「架构没用」而是「**架构的杠杆是【交互结构 × 任务结构】的交互**」—— 前者会被前人一句反例推翻，后者站得住。
2. **★ 判据带"怎么被证伪"**
   层 3 直接给出判死门：机制主张若成立，**拆掉它应当改善** ⇒ 训练内分离 + 留出无分离 = 完整判死门形态。
3. **★ 血泪纪律写成硬规则，不是感想**
   「行数 ≠ 有效分母」「零分辨力尺子先剔除」「失败支必须显式记账」「不可分辨 ≠ 无效应」—— 每一条背后都是一次真实的判错。

---

## 安装

```bash
git clone https://github.com/lixvanran/creativity-mechanism-skills.git
cp -r creativity-mechanism-skills/skills/<skill-name> ~/.claude/skills/    # 或你的 skill 目录
```

★ 每个 skill 目录标准布局：`SKILL.md`（frontmatter + 触发条件 + 结论 + 怎么用 + 硬纪律）＋ `scripts/`（可运行）＋ `references/`（预注册、判决、证据）。

---

## 自检

```bash
# 层 3：零判官空间度量 + 前人口径对齐
python3 skills/learning-route-generalization/scripts/space.py
python3 -c "import sys; sys.path.insert(0,'skills/learning-route-generalization/scripts'); import space, metrics_priorart; print('ok')"

# 层 4：状态机内核 + ★ 变异注入测试（证明测试不是空转）
python3 skills/state-driven-agent/scripts/test_state_layer.py
python3 skills/state-driven-agent/scripts/test_state_layer_rev3_mutations.py

# 层 4：状态机内核（★ 实测 8/8 通过 · exit 0 · 含变异注入）
python3 skills/state-driven-agent/scripts/test_state_layer.py
python3 skills/state-driven-agent/scripts/test_state_layer_rev3_mutations.py

# 完整性
sha256sum -c SHA256SUMS.txt
```

★ **层 2 与层 4 的 scripts 需要 `MINIMAX_SUBSCRIPTION_KEY` 才能真正跑批**（`client.py`）；★ 纯度量与状态机内核不依赖网络。

---

## 目录

```
skills/
  design-route-space-expansion/    层2 · 设计路线
    SKILL.md
    scripts/  arm3.py(FRAMES/PERSONAS/diverge) dual.py run_compare5.py client.py …
  learning-route-generalization/   层3 · 学习路线
    SKILL.md
    scripts/  space.py metrics_priorart.py nested_calib_self.py analyze_batch.py + 3 个独立复核脚本
    references/ 5 份预注册与题集规格 + 实验报告 + KNOWN_ISSUES
  state-driven-agent/              层4 · 状态机
    SKILL.md
    scripts/  state_layer.py apply_state_layer_rev3.py test_state_layer.py + 变异测试 + 探针
    references/ ADHD 特质→Agent 实现路径 + 实验报告
```

★ 过程材料（跑批输出、会话记录、工具内部实现、论文交差件）**不在本仓** —— 那是过程仓的事；本仓只放**成品**。

---

## License

MIT —— 见 [LICENSE](LICENSE)。

★ **引用这些 skill 时请保留各自 SKILL.md 里的"硬纪律"与"不能支撑什么"** —— 那些不是免责声明，是结论的一部分。
