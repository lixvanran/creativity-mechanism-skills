"""臂3 / 臂4 · 双轴架构。**两者的唯一差异是末步。**

轴A VARIANCE  → 每个分支一个独立调用，零共享上下文（治链内锚定）
轴B PARTITION → 跨模型档位 + 不同 persona（治知识不分区）

末步两种：
  fuse   —— 把分支材料综合成一篇答复（融合门）
  select —— 各分支已各自成篇，末步只挑一篇，原样输出

规格、认知框架、persona 全部放在 prompts.py，与代码分离，
这样 leakage.py 能只扫「真正发给模型的字符串」。
"""
from creativity_lab.arms.base import ArmResult
from creativity_lab.client import MODELS
from creativity_lab.prompts import (FRAMES, PERSONAS, OUT_SPEC, PREMISE_Q,
                                    BRANCH_ASK, FUSE_ASK, SELECT_ASK)

N_BRANCH = 5


def _branch_specs():
    """轴A × 轴B 的联合扇出：框架/模型/persona 三者错位绑定。"""
    return [(FRAMES[i % len(FRAMES)], MODELS[i % len(MODELS)], PERSONAS[i % len(PERSONAS)])
            for i in range(N_BRANCH)]


class Dual:
    """mode='fuse' → 臂3；mode='select' → 臂4。发散层完全相同。"""

    def __init__(self, mode: str, select: str = "greedy"):
        assert mode in ("fuse", "select")
        self.name = f"dual_{mode}"
        self.mode, self.select = mode, select

    # ---------- 发散层 ----------
    def _diverge(self, llm, topic, *, produce_article: bool):
        specs = _branch_specs()
        outs = []
        for (frame, model, persona) in specs:
            prompt = (BRANCH_ASK.format(
                topic=topic["ask"], frame_name=frame["name"], frame_text=frame["text"],
                persona=persona, spec=OUT_SPEC,
                extra="\n直接写出**完整的答复本身**，不要写判断片段。" if produce_article
                     else "\n写出这个位置上会看到的**判断与依据**，不要写成文。"))
            outs.append(llm.chat(prompt, model=model, purpose=f"diverge:{model}"))
        return [o for o in outs if o]

    # ---------- 臂3：融合门 ----------
    def _fuse(self, llm, topic, frags):
        pre = llm.chat(PREMISE_Q.format(n=len(frags), cands="\n\n".join(
            f"[{i+1}] {c[:400]}" for i, c in enumerate(frags))), purpose="premise")
        return llm.chat(FUSE_ASK.format(topic=topic["ask"],
                                        frags="\n\n".join(f"[{i+1}] {c[:400]}" for i, c in enumerate(frags)),
                                        pre=pre[:700], spec=OUT_SPEC), purpose="fuse")

    # ---------- 臂4：只选不融 ----------
    def _select(self, llm, topic, arts):
        return llm.chat(SELECT_ASK.format(
            n=len(arts),
            arts="\n\n=====\n\n".join(f"[第{i+1}篇]\n{a}" for i, a in enumerate(arts)),
            spec=OUT_SPEC), purpose="select")

    def run(self, llm, topic, rep):
        if self.mode == "fuse":
            frags = self._diverge(llm, topic, produce_article=False)
            text = self._fuse(llm, topic, frags) if frags else ""
        else:
            arts = self._diverge(llm, topic, produce_article=True)
            text = self._select(llm, topic, arts) if arts else ""
        return ArmResult(self.name, topic["tid"], rep, text, len(frags if self.mode == "fuse"
                                                                  else arts) if text else 0)
