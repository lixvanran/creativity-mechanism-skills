# -*- coding: utf-8 -*-
"""arms_b2.py —— v2b 臂（★ 签名从事前约束改为事后验收 ★）

★ 与 arms_b.B2 的唯一差别：★★
  arms_b （v2 原型）：生成提示 = brief + 签名要点  ⇒ ★ 分支被推窄 ★
  arms_b2（v2b）：   生成提示 = brief 【只有 brief】⇒ 签名只用于【事后核对】★★
★ 其余完全相同（实体类别自举、双轨取轴、落地性闸门、合流）⇒ ★ 干净的单变量对照 ★
"""
from __future__ import annotations
import os
HERE = os.path.dirname(os.path.abspath(__file__))
import arms_b
import parse_b

p_branch = arms_b.p_branch
p_merge = arms_b.p_merge
p_base = arms_b.p_base
p_skillv2_entities = arms_b.p_skillv2_entities
axes_block = arms_b.axes_block
with_strict = arms_b.with_strict


def p_branch_v2b(topic, rewrite, signature):
    """★ 生成提示里【不放签名】⇒ ★ 签名只用于事后核对 ★"""
    return ("任务：%s\n\n你被指定只走这一条路线，不要混入别的路线：\n路线：%s\n"
            "注意：必须真的按这条路线做，而不是换个说法。%s"
            % (topic["prompt"], rewrite, arms_b.FORM))


V2B_PLAN = """你将使用「思维面扩展」规程 v2 来完成这个任务。

【路径轴库】
{axes_block}

【规程 v2 · 三步】
第 0 步 列实体类别：先想清楚这道题里有哪些【可核验的对象类别】？每类给 2-3 个具体例子。
  ★ 只在这个领域【内部】的对象类别里想；★ 不要引入题域之外的目标 ★
第 1 步 双轨取轴：轨 A 从【路径轴库】挑（过程轴）；轨 B 从第 0 步的【实体类别】里挑（实体域轴）。
  两轨合并去重，★ 总共留 3-5 条 ★
第 2 步 落地性闸门 + 签名：
  ★ 每条轴必须能落到第 0 步的某个实体类别上 ⇒ 在 grounded_in 里写明它落在哪一类 ★；★ 落不上去的轴【不成立】、★ 不要选它 ★
  再写 2 个正签名（只有真走这条路才会在答案里出现的、具体可观察的要点；写名词或动作）、1 个反签名、1 个代价。
只输出 JSON：
{{"entities":[{{"category":"对象类别名","examples":["具体例子1","具体例子2"]}}],
  "paths":[{{"axis":"轴名","source":"A或B","grounded_in":"落在哪个实体类别","rewrite":"这条路在这道题上的具体做法（1-2句）","signature":["要点1","要点2"],"antisignature":"不该出现的东西","cost":"代价"}}]}}"""


def p_skillv2b_plan(topic, entities_text):
    head = ("任务：%s\n\n【你刚才列出的可核验对象类别】\n%s\n\n"
            % (topic["prompt"], entities_text))
    return head + V2B_PLAN.format(axes_block=axes_block())
