"""shim —— 真实实现在 `creativity_lab/state_layer.py`；本文件仅为 `from state_layer import ...` 兼容。"""
from creativity_lab.state_layer import *  # noqa: F401,F403
from creativity_lab.state_layer import (  # noqa: F401
    State, Hypothesis, Subgoal, Attempt, KeepPoint,
    propose_subgoal, revoke_subgoal, revise_subgoal,
    add_evidence, rollback, record_attempt, record_call, detect_tie,
)
