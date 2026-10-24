"""臂3/臂4 共享的双轴发散架构。

两轴都在代码里，不是提示词里的叙述：
  轴A VARIANCE → 治 fixation：5 个完全隔离的调用，各自一个认知框架
  轴B PARTITION → 治无知识分区：跨 MiniMax 5 个规模档位 + 5 个普通 persona

措辞纪律：框架 / persona / 提问里**不出现**评价口径的词（新颖、可检验、框架转换、
高光、立场代价……），也不出现任何题面元素。那等于给答案打标签。
"""
import client2 as C
from shared import OUT_SPEC, VALIDATE_Q

# 认知框架：vantage operator（换一个提问位置），不是身份、不是专家人设
FRAMES = [
    ("长时段尺度", "把时间尺度拉到数十年到数百年。同一类现象在更长周期里反复出现过什么形态？它这次的量级和结构有什么不同？"),
    ("系统承载力", "把规模推到极限。这个系统在什么量级上会开始失稳？先崩的是哪一环？承载力由什么决定？"),
    ("反面案例", "找做对的事后来是怎么崩的。当时没人看见的信号是什么？事后能看清、事前看不见的是什么？"),
    ("无利害观察者", "假设你对这件事没有任何利害关系，既不受益也不受损。你会怎么描述它？"),
    ("亲历者视角", "如果这件事真的发生，一个生活被它直接改变的人会怎么过一天？他的具体动作和妥协是什么？"),
    ("硬约束", "先不谈趋势，只谈硬边界：物理的、资源的、制度的。哪些东西是不管多想都不可能变的？"),
    ("二阶效应", "假设第一阶效果已经被普遍接受并内化了。那剩下的那个让人不满意的第二阶问题是什么？"),
]

# 普通 persona：只给身份与生活状态，**不含任何任务线索**。
PERSONAS = [
    "你是一名 1962 年出生、在国营机械厂车间干了三十一年的退休工人。",
    "你是一名 1998 年出生、在城市做零工、租住在城中村的年轻人，识字不多但对街面上的事极其敏感。",
    "你是一名 1975 年出生、在县城开了一家小诊所的家庭医生，一辈子处理的是人和身体。",
    "你是一名 2003 年出生、刚工作两年的年轻人，关心自己这一代会被定义成什么。",
    "你是一名 1955 年出生、在报社做了四十年国际新闻的退休编辑，见证过三次技术乐观主义的落空。",
]

# 轴B 的模型轮换：跨规模档位（不同训练 → 部分不同的知识分布）
AXIS_B_MODELS = ["MiniMax-M3", "MiniMax-M3.1-Flash-Preview", "MiniMax-M2.7",
                 "MiniMax-M2.5", "MiniMax-M2.1"]

DIAG = []


def diverge(n=5, workers=1, topic=None):
    """轴A × 轴B 的联合扇出：5 个完全隔离的调用。"""
    DIAG.clear()
    prompts, models = [], []
    for i in range(n):
        fname, fprompt = FRAMES[i]
        prompts.append(
            f"问题：{topic}\n\n"
            f"你现在从【{fname}】这个认知位置出发去看这个问题。\n{fprompt}\n\n"
            f"设定：{PERSONAS[i]}\n\n"
            f"直接写出你的判断和依据，200-400字。\n- {OUT_SPEC}"
        )
        models.append(AXIS_B_MODELS[i])
    outs = C.par(prompts, n, models=models, workers=workers)
    for i, o in enumerate(outs):
        DIAG.append(dict(model=models[i], frame=FRAMES[i][0],
                        ok=bool(o and len(o) > 60), chars=len(o or "")))
    return [o for o in outs if o and len(o) > 60]


def deep_validate(cands, topic=None):
    """前提审查。中性措辞：不问『是否不寻常』，只问『依赖什么前提』。"""
    joined = "\n\n---\n".join(f"[{i+1}] {c[:400]}" for i, c in enumerate(cands))
    return C.chat("下面是若干份关于同一问题的独立判断。\n\n" + joined +
                  "\n\n" + VALIDATE_Q + "\n\n150-250字。")


def deception_check(cands, deep, topic=None):
    """反诘：这套判断隐含的『什么算好』是什么，它会把人带到哪个死胡同。"""
    return C.chat(
        "你刚才在这些判断中隐含了一个『什么算好』的标准。\n\n"
        "这些判断：\n" + "\n".join(f"[{i+1}] {c[:180]}" for i, c in enumerate(cands)) +
        "\n\n对它们前提的分析：\n" + deep[:400] +
        "\n\n请明确回答：你隐含的『好』是什么？沿着这个标准走下去，最可能把判断带进哪个死胡同？"
        "有没有一个它系统性高估、但其实不成立的东西？100-200字。")
