"""★ 实验包依赖的【显式声明】与【可执行的错误提示】★

============================================================
★ 为什么要有这个文件（★ 2026-10-25 维护时发现 ★）
============================================================
★ 事件：★ 本仓的三个层2 脚本（`adhd_repro.py` / `dual.py` / `run_compare5.py`）
★   全部 `from creativity_lab.… import …`，★ 而 `creativity_lab`（实验包）**不在本仓** ⇒
★   ⇒ ★ 照 README 装完直接 import 就炸：**裸 ModuleNotFoundError** ★
★   ⇒ ★ 读者看不出"缺的是哪个仓、怎么补、能不能就地补" ★
============================================================

★ **为什么【不就地 vendor】**（★ 这是本项目的硬纪律：★ 不得改变被测量 ★）
------------------------------------------------------------
★ 仓内的平铺模块（`client.py` / `arm3.py` / `shared.py` / `topics4.py`）
★   与实验包 `creativity_lab/` 的对应模块**已经不是同一版**：
★   - `arm3.py.FRAMES`（tuple 版）★ vs 实验包 `prompts.py.FRAMES`（dict 版）★ ⇒ **内容不同**
★   - `client.py`（仓内）★ vs `creativity_lab/client.py`（实验包）★ ⇒ **sha256 不同**
★ ⇒ ★★ **就地 vendor 会把臂的内容换掉** ★ ⇒ ★★ 而臂的内容就是被测量本身 ★
★ ⇒ ★★ ⇒ 所以这里**只做一件事：★ 把依赖写清楚、★ 让缺依赖时报出可执行的提示 ★★

============================================================
★ 怎么补上这个依赖（★ 唯一正确的做法 ★）
============================================================
    # 从实验仓取 creativity_lab（★ 它与本仓的臂内容同源 ★）
    export PYTHONPATH=/path/to/实验仓:$PYTHONPATH
    python3 skills/design-route-space-expansion/scripts/dual.py --help

★ 若要用【本仓】的平铺模块（★ 臂3/臂4 那一代 ★）★ 请直接用 `arm3.py`（★ 它不依赖实验包 ★）。

============================================================
★ 本文件零依赖、零网络、零额度（★ 只做检查与提示 ★）
============================================================
"""

from __future__ import annotations

import importlib
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# ★ 各脚本需要的具体符号（★ 写清楚 ⇒ 报错时读者知道自己缺什么 ★）★
NEEDS = {
    "adhd_repro": [("creativity_lab.client", "LLM")],
    "dual": [("creativity_lab.arms.base", "ArmResult"),
             ("creativity_lab.client", "MODELS"),
             ("creativity_lab.prompts", "FRAMES, PERSONAS, OUT_SPEC, PREMISE_Q, "
                                        "BRANCH_ASK, FUSE_ASK, SELECT_ASK")],
    "run_compare5": [("creativity_lab.learnarch", "run_episode"),
                     ("creativity_lab.client", "LLM"),
                     ("creativity_lab.adhd_repro", "run_adhd")],
}


def _msg(script: str, missing: str) -> str:
    need = NEEDS.get(script, [])
    lines = [
        "",
        "✘ 缺少实验包依赖：`%s`" % missing,
        "★ 本仓（creativity-mechanism-skills）**不包含**实验包 `creativity_lab` ⇒",
        "★ 这是【有意的】：★ 本仓的平铺模块（arm3.py / client.py）与实验包的对应模块",
        "★ **已经不是同一版**（★ FRAMES/PERSONAS 与 client 的 sha256 都不同 ★）⇒",
        "★ **就地 vendor 会改掉臂的内容** ★ ⇒ ★ 而臂的内容就是被测量本身 ★",
        "",
        "★ 怎么补：★ 从实验仓取 `creativity_lab`，然后：",
        "      export PYTHONPATH=/path/to/实验仓:$PYTHONPATH",
        "",
    ]
    if need:
        lines.append("★ 本脚本需要的符号（★ 供你核对是不是同一代 ★）：")
        for mod, syms in need:
            lines.append("      · %-28s → %s" % (mod, syms))
        lines.append("")
    lines += [
        "★ 若你要的是【本仓自带的】臂3/臂4（★ 不依赖实验包 ★）：",
        "      python3 skills/design-route-space-expansion/scripts/arm3.py",
        "",
    ]
    return "\n".join(lines)


def require(script: str) -> None:
    """★ 在 import 实验包之前调用它 ★
    ⇒ ★ 缺依赖时抛【带可执行提示】的 ImportError（★ 不是裸 ModuleNotFoundError ★）"""
    for mod, _syms in NEEDS.get(script, []):
        try:
            importlib.import_module(mod)
        except ImportError as e:
            raise ImportError(_msg(script, mod)) from e


def available(script: str) -> bool:
    """★ 只做检查、不抛异常（★ 供自检脚本用 ★）"""
    for mod, _syms in NEEDS.get(script, []):
        try:
            importlib.import_module(mod)
        except ImportError:
            return False
    return True
