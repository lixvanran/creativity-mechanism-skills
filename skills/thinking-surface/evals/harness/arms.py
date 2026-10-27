"""实验臂定义。

五臂同题对打，全部用同一模型、同一温度、同一字数上限、同一题面：

  A0_base      1 次调用，裸题面                       —— 基线
  A1_persona   4 次调用，每次一个专业身份              —— 「换人格」这个最常见的做法
  A2_onemulti  1 次调用，一次性要求 4 条不同做法       —— 「一句话让模型多角度想」这个最省的做法
  A3_contract  1 次测绘 + 4 次按分支生成 + 兑现审计    —— 本设计：路径合约（分支由模型自己测绘）
  A3c_curated  4 次按【预注册轴】生成 + 兑现审计        —— 本设计的上界：分支由外部给定
  A4_h0        1 次测绘 + 4 次按【任务无关维度】生成      —— H0 臂：结构相同但分支内容与任务无关

A3 与 A3c 的差别 = 「谁来选分支」；A3 与 A4 的差别 = 「分支是否与任务相关」。
两者都必要：缺 A3c 无法说清机制上限，缺 A4 无法杀死「只是结构有效」。
"""
from __future__ import annotations

# A1 用的 4 个专业身份。刻意做成「覆盖设计空间」的强基线（不是稻草人）：
# 每个身份有自己的关注面（用于兑现率审计），关注面与预注册轴用词不同，避免直接送答案。
ROLES = [
    {
        "id": "R1",
        "title": "资源与执行负责人",
        "focus": ["预算", "人手", "执行"],
        "desc": "你关心这件事能不能真正落地：需要多少预算、多少人、多久能做完，阻力在哪。",
    },
    {
        "id": "R2",
        "title": "激励与成本设计者",
        "focus": ["成本", "激励", "收费"],
        "desc": "你关心这件事的经济学：谁付钱、付多少、行为怎么被改变、收益和成本怎么算。",
    },
    {
        "id": "R3",
        "title": "体验与形式设计者",
        "focus": ["体验", "现场", "呈现"],
        "desc": "你关心人的感受与呈现形式：参与者的动线、感受、第一次接触时的画面。",
    },
    {
        "id": "R4",
        "title": "关系与社群组织者",
        "focus": ["社群", "关系", "动员"],
        "desc": "你关心人与人的连接：谁和谁搭上、关系怎么建立、如何被动员起来。",
    },
]

# A4（H0）用的任务无关维度：它们**套在任何任务上都说得通**，但不是从任务本身推出来的。
# 若 A4 ≈ A3，说明「有效」的是「分支结构」而非「任务相关的路径选择」。
GENERIC_DIMENSIONS = [
    {"id": "G1", "label": "时间尺度轴", "brief": "从时间尺度切入：拉长看、压缩看、分阶段看。"},
    {"id": "G2", "label": "成本量级轴", "brief": "从成本量级切入：按数量级分档看。"},
    {"id": "G3", "label": "社会关系轴", "brief": "从社会关系切入：看人与人之间谁影响谁。"},
    {"id": "G4", "label": "物理约束轴", "brief": "从物理约束切入：看空间、材料、容量等硬条件。"},
    {"id": "G5", "label": "信息对称轴", "brief": "从信息对称切入：看谁知道什么、谁不知道什么。"},
    {"id": "G6", "label": "历史纵深轴", "brief": "从历史纵深切入：看这件事过去怎么演化、惯例从哪来。"},
]

FORM = "请具体说明做法，包含：核心机制、关键步骤、可能的代价或风险。控制在 300-600 字。"


def p_base(topic) -> str:
    return topic["prompt"]


def p_persona(topic, role) -> str:
    return (
        f"你是一位{role['title']}。{role['desc']}\n\n"
        f"任务：{topic['prompt']}\n\n"
        f"要求：站在该角色的专业立场作答，你的方案必须真实体现这个角色最关心的问题，"
        f"不要写成四平八稳的通用答案。{FORM}"
    )


def p_onemulti(topic) -> str:
    return (
        f"任务：{topic['prompt']}\n\n"
        f"请先独立思考 4 条**明显不同**的做法——它们的机制必须真的不同，"
        f"不能只是换个说法、换个身份或换个措辞角度；然后分别给出每条做法下的具体方案，"
        f"最后再写一段综合说明。{FORM}"
    )


MAP_INSTRUCTION = """请先做「决策点测绘」，再设计路径。
第 1 步：把这个任务拆成一串关键决策点（3-6 个）。对每个决策点，列出 2-3 个**实质不同**的做法。
  判定标准：两条做法的差别必须体现在最终方案的做法/机制上；
  仅仅换个说法、换个身份、换个角色、换个措辞角度、换个人设的**不算**不同做法。
第 2 步：为每条做法写一个「签名」——2 个只有真正走这条做法才会在答案里出现的、具体可观察的要点。
  签名要具体到名词或动作；禁止写"认真""重视""创新""用心"这类空话。
只输出 JSON，不要任何解释：
{"forks":[{"decision":"决策点名称","branches":[{"label":"做法名","brief":"这条路线的具体做法（1-2句）","signature":["要点1","要点2"]}]}]}"""


def p_map(topic) -> str:
    return f"任务：{topic['prompt']}\n\n{MAP_INSTRUCTION}"


def p_branch(topic, brief, signature) -> str:
    sig = "、".join(signature) if signature else "（无）"
    return (
        f"任务：{topic['prompt']}\n\n"
        f"你被指定只走这一条路线，不要混入别的路线：\n"
        f"路线：{brief}\n"
        f"这份方案必须真实体现以下要点：{sig}。\n"
        f"注意：只在方案里提一句不算，必须真的按这个要点做。{FORM}"
    )


def p_branch_curated(topic, axis) -> str:
    return (
        f"任务：{topic['prompt']}\n\n"
        f"你被指定只走这一条路线，不要混入别的路线：\n"
        f"路线：{axis['feed']}\n"
        f"注意：必须真的按这条路线做，而不是换个说法。{FORM}"
    )


def p_branch_generic(topic, dim) -> str:
    return (
        f"任务：{topic['prompt']}\n\n"
        f"你被指定只走这一条路线，不要混入别的路线：\n"
        f"路线：{dim['brief']}\n"
        f"注意：必须真的按这条路线做，而不是换个说法。{FORM}"
    )


# 兑现率审计：uniform brief → 所有臂可比
AUDIT_INSTRUCTION = """判断：正文是否**实质**体现了这条路线？
标准：正文里能看到路线所说的实际做法（展开成步骤或机制），而不是只提了一句关键词，
      或者虽然用了词但明显还是另一条路线的做法。
只输出 JSON：{"hit":true或false,"reason":"不超过20个字"}"""


def p_audit(topic, brief, text) -> str:
    return (
        f"任务：{topic['prompt']}\n"
        f"这份方案应当走这一条路线：{brief}\n\n"
        f"方案正文：\n{text}\n\n{AUDIT_INSTRUCTION}"
    )


SKELETON_INSTRUCTION = """请抽出这份方案的「核心机制骨架」：3-6 个短语，说明它**到底用了哪些做法/机制**
（要写做法本身，不是主题词）。
同时判断：
  vague     : 方案是否基本是空话套话（没有具体做法）？
  actionable: 方案的具体可执行程度，1-5（1=完全空话，5=可直接照做）
  on_topic  : 是否在回答这个任务？
只输出 JSON：{"skeleton":["...","..."],"vague":true或false,"actionable":1到5,"on_topic":true或false}"""


def p_skeleton(topic, text) -> str:
    return (
        f"任务：{topic['prompt']}\n\n"
        f"方案正文：\n{text}\n\n{SKELETON_INSTRUCTION}"
    )
