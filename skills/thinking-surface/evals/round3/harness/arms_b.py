# -*- coding: utf-8 -*-
"""arms_b.py —— 路 B 的三个臂（★ 真实题 + 外部金标 ★）

B0_baseline : 裸题，1 次
B1_skillv1  : ★ skill v1 规程（从 13 条通用轴库挑 → 改写成本题语言 → 签名 → 隔离生成 → 保留分歧合流）★
B2_skillv2  : ★ skill v2 规程（★ 先列【实体类别】★ → 双轨取轴 → 落地性闸门 → 签名 → 隔离生成 → 合流）★

★ 公平性：★ B1/B2 的规程文本都【从 skill 源文件现读】★（SKILL.md + references/path-recipes.md）
  ⇒ ★ 测的是【skill 本身】、不是它的一份拷贝 ★
★ 成本差异（★ B1/B2 的 context 明显更大 ★）⇒ 必须并排报 token 成本 ★
"""
from __future__ import annotations
import os

SKILL_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")
FORM = "请具体说明做法，包含：核心机制、关键步骤、可能的代价或风险。控制在 300-600 字。"


def _read(rel):
    with open(os.path.join(SKILL_ROOT, rel), encoding="utf-8") as f:
        return f.read()


def skill_text():
    return _read("SKILL.md")


def axis_library():
    """★ 运行时解析轴库（★ 与 round2 同一套逻辑 ★）"""
    import re
    first = _read("references/path-recipes.md").split("## 2.")[0]
    axes = []
    for line in first.splitlines():
        m = re.match(r"^\|\s*\*\*(.+?轴)\*\*\s*\|(.+?)\|(.+?)\|\s*$", line.strip())
        if m:
            axes.append({"label": m.group(1).strip(), "ask": m.group(2).strip(),
                         "example": m.group(3).strip()})
    if len(axes) < 5:
        raise RuntimeError("轴库解析失败：%d 条" % len(axes))
    return axes


def axes_block():
    return "\n".join("%d. %s | 它在问什么：%s | 做法示例：%s"
                     % (i + 1, a["label"], a["ask"], a["example"])
                     for i, a in enumerate(axis_library()))


def p_base(topic):
    return topic["prompt"]


# ───────────────────────── B1：skill v1 ─────────────────────────
V1_PLAN = """你将使用「思维面扩展」规程来完成这个任务。
该规程的核心资产是【预置路径轴库】——你必须【从库里挑】、不要自己现编。

【路径轴库】
{axes_block}

【规程】
第 1 步 选轴：从库里挑 3-5 条（别贪多）。
第 2 步 改写：把每条选中的轴【改写成这道题的具体做法】。照抄轴名 = 没改。
第 3 步 签路径：为每条路径写 2 个正签名（只有真走这条路才会在答案里出现的、具体可观察的要点；写名词或动作；禁止"认真""重视""创新"这类空话）、
         1 个反签名（这条路上不该出现的东西）、1 个代价（这条路牺牲什么、谁会不满意）。
只输出 JSON，不要任何解释：
{{"paths":[{{"axis":"轴名","rewrite":"这条路在这道题上的具体做法（1-2句）","signature":["要点1","要点2"],"antisignature":"不该出现的东西","cost":"代价"}}]}}"""


def p_skillv1_plan(topic):
    return "任务：%s\n\n%s" % (topic["prompt"], V1_PLAN.format(axes_block=axes_block()))


# ───────────────────────── B2：skill v2 ─────────────────────────
V2_PLAN = """你将使用「思维面扩展」规程 v2 来完成这个任务。
该规程的核心资产仍是【预置路径轴库】；v2 在它前面加了一步、在它后面加了一道闸。

【路径轴库】
{axes_block}

【规程 v2 · 四步】
第 0 步（★ 新 ★）列实体类别：
  先想清楚：这道题里有哪些【可核验的对象类别】？每类给 2-3 个具体例子。
  ★ 这一步的作用是【不跑出题域】：只在这个领域内部的对象类别里想，★ 不引入题域之外的目标（如"去大厂就业"）★。
第 1 步 双轨取轴：
  轨 A：从【路径轴库】里挑 3-5 条（★ 过程轴：事情怎么组织 ★）
  轨 B：从第 0 步的【实体类别】里挑（★ 实体域轴：有哪些类型的对象可选 ★）
  两轨合并去重，★ 总共留 3-5 条 ★（别贪多，轴太多会互相重合）
第 2 步 落地性闸门 + 签名：
  ★ 每条轴必须能落到第 0 步的某个实体类别上 ⇒ 在 grounded_in 里写明它落在哪一类 ★
  ★ 落不上去的轴【不成立】⇒ 不要选它 ★
  再写 2 个正签名（只有真走这条路才会在答案里出现的、具体可观察的要点；写名词或动作）、1 个反签名、1 个代价。
只输出 JSON，不要任何解释：
{{"entities":[{{"category":"对象类别名","examples":["具体例子1","具体例子2"]}}],
  "paths":[{{"axis":"轴名","source":"A或B","grounded_in":"落在哪个实体类别","rewrite":"这条路在这道题上的具体做法（1-2句）","signature":["要点1","要点2"],"antisignature":"不该出现的东西","cost":"代价"}}]}}"""


# ★ v2 的第 0 步单独一次调用（★ schema 简单、★ 实测：★ 复杂嵌套 schema 模型会不遵守 ★）
V2_ENTITIES = """先想清楚：这道题里有哪些【可核验的对象类别】？每类给 2-3 个具体例子。

★ 重要：★ 只在这个领域【内部】的对象类别里想 —— ★ 不要引入题域之外的目标 ★
（★ 例如一道"怎么选大学"的题里，"去大厂就业"不是这题的答案域 ★）。
只输出 JSON：{{"categories":[{{"category":"对象类别名","examples":["具体例子1","具体例子2"]}}]}}"""


def p_skillv2_entities(topic):
    return "任务：%s\n\n%s" % (topic["prompt"], V2_ENTITIES)


def p_skillv2_plan(topic, entities_text):
    """★ 第 1-2 步：★ 把第 0 步自举的实体类别喂回去、★ 再双轨取轴 ★"""
    block = V2_PLAN.format(axes_block=axes_block())
    head = ("任务：%s\n\n【你刚才列出的可核验对象类别】\n%s\n\n"
            % (topic["prompt"], entities_text))
    return head + block


# ───────────────────────── 生成 / 合流 ─────────────────────────
def p_branch(topic, rewrite, signature):
    sig = "、".join(signature) if signature else "（无）"
    return ("任务：%s\n\n你被指定只走这一条路线，不要混入别的路线：\n路线：%s\n"
            "这份方案必须真实体现以下要点：%s。\n注意：只在方案里提一句不算，必须真的按这个要点做。%s"
            % (topic["prompt"], rewrite, sig, FORM))


MERGE = """下面是多条**互相独立**的方案（每条走了不同的路线）。请做【保留分歧的合流】：
- 逐条列出每个方案、它覆盖的决策点、它的代价；
- 明确指出它们之间**真正的冲突点**（★ 冲突是资产：★ 它告诉用户"你在这儿必须选一个" ★）；
- **不要**取交集、**不要**投票、**不要**综合成一个"最优解"；
- 最后列出需要用户拍板的取舍项。
不要评价哪个方案更好。"""


def p_merge(topic, branches):
    body = "\n\n".join("【方案 %d】%s" % (i + 1, b) for i, b in enumerate(branches))
    return "任务：%s\n\n%s\n\n%s" % (topic["prompt"], body, MERGE)


STRICT_SUFFIX = """

★ ★ 硬要求 ★：★ 上一轮输出的路径不足 3 条 ⇒ ★ 这一轮必须给满 3 到 5 条 ★
★ 每条 path 都要有 axis / rewrite / signature（2 个）/ antisignature / cost 五个字段 ★
★ 只输出那一个 JSON 对象、★ 不要在它前后加任何别的字段 ★"""


def with_strict(prompt):
    return prompt + STRICT_SUFFIX
