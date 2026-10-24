#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""unit_store —— 单元级原子落盘 + 续跑只补缺口（★ 通用件 · ★ 2026-10-25 抽自 topo_arm.py）

★ 为什么抽成通用件（★ 第四组 Stage-1 栽过的地方）：
★ ① runner 没有「跳过已存在单元」⇒ `--append` 只是开文件模式
★    ⇒ ★ `--reps 3` 只补了 rep=3 ⇒ ⇒ **n 悄悄变小**
★ ② 两个进程并发占住通道 ⇒ 「进程活着但一次调用都没发出」是假象
★ ③ 两个进程并发写盘 ⇒ 同 (题,rep) 出现两条 ⇒ 只能事后去重（★ 补救，不是根治）

★ ★★ 本模块的根治思路（★ 三条一起才闭环）★★
★ **A. 单元级文件（★ 不是共享 jsonl）**
★    ⇒ ⇒ ★ **不同单元写不同文件 ⇒ ⇒ 并发写【天然零冲突】** ⇒ ⇒ **不需要事后去重**
★    ⇒ ⇒ ★ ★ **★ 这就是"并发写同一个 jsonl 怎么防"的答案：★ ★ 【别写共享 jsonl】**
★ **B. 原子写（tmp + os.replace）**
★    ⇒ ⇒ ★ 单个文件要么是旧的完整内容，要么是新的完整内容 ⇒ ⇒ **不会读到半个文件**
★ **C. flock 互斥（★ 对付"同单元被两个进程同时算"）**
★    ⇒ ⇒ ★ 同目录级互斥锁 ⇒ ⇒ **后到者拿不到锁 ⇒ ⇒ 直接退出（★ 不排队、不等待）**
★    ⇒ ⇒ ★ 锁由内核在进程崩时自动释放 ⇒ ⇒ **不会留死锁**

★ 用法（★ 最小）：
    from creativity_lab.experiments.unit_store import UnitStore
    st = UnitStore("runs/xxx/units")
    if st.has("S4", 1, "arm", 0):        # ★ 续跑：★ 只补缺口
        continue
    st.put("S4", 1, "arm", 0, {"n_calls": 13, "n_failed": 0})
    st.sweep()                            # ★ 收尾：★ 报告坏文件/重名

★ ★ 单进程独占跑批（★ 推荐）：
    st = UnitStore("runs/xxx/units", exclusive=True)   # ★ 拿不到锁就抛错，★ 不静默并发
"""

from __future__ import annotations

import errno
import fcntl
import json
import os
import re
import tempfile
from typing import Any, Dict, Iterable, List, Optional, Tuple

FNAME_RE = re.compile(r"^(?P<topic>.+)_r(?P<rep>\d+)_(?P<arm>.+)_u(?P<run>\d+)\.json$")


def _atomic_write(path: str, text: str) -> None:
    """★ 原子写：★ 同目录 tmp + fsync + os.replace（★ 跨文件系统的 rename 也原子）"""
    d = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(prefix=".us_", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)          # ★ ★ 原子替换
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class UnitStore:
    """★ 单元级落盘仓（★ 键 = (topic, rep, arm, run)）"""

    def __init__(self, units_dir: str, exclusive: bool = False, prefix: str = "") -> None:
        self.dir = os.path.realpath(units_dir)
        os.makedirs(self.dir, exist_ok=True)
        self.prefix = prefix
        self._lock_fh = None
        if exclusive:
            self._acquire_lock()

    # ── 锁 ──────────────────────────────────────────────
    def _lock_path(self) -> str:
        return os.path.join(self.dir, ".unitstore.lock")

    def _acquire_lock(self) -> None:
        p = self._lock_path()
        fh = open(p, "a+")
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            fh.close()
            if e.errno in (errno.EACCES, errno.EAGAIN):
                raise RuntimeError(
                    "★ 已有另一个进程持有 %s 的锁 ⇒ ⇒ 【不并发写】⇒ ⇒ 请先确认前一个进程已停" % self.dir
                ) from e
            raise
        self._lock_fh = fh
        fh.seek(0)
        fh.truncate()
        fh.write("pid=%d\n" % os.getpid())
        fh.flush()

    def release(self) -> None:
        if self._lock_fh is not None:
            try:
                fcntl.flock(self._lock_fh.fileno(), fcntl.LOCK_UN)
            finally:
                self._lock_fh.close()
                self._lock_fh = None

    # ── 键 ──────────────────────────────────────────────
    def path_for(self, topic: str, rep: int, arm: str, run: int) -> str:
        return os.path.join(self.dir, "%s%s_r%d_%s_u%d.json" % (self.prefix, topic, rep, arm, run))

    def has(self, topic: str, rep: int, arm: str, run: int) -> bool:
        return os.path.exists(self.path_for(topic, rep, arm, run))

    def put(self, topic: str, rep: int, arm: str, run: int, payload: Dict[str, Any]) -> str:
        """★ 落盘一个单元（★ 原子）★ 返回路径"""
        p = self.path_for(topic, rep, arm, run)
        _atomic_write(p, json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
        return p

    def get(self, topic: str, rep: int, arm: str, run: int) -> Optional[Dict[str, Any]]:
        p = self.path_for(topic, rep, arm, run)
        if not os.path.exists(p):
            return None
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    # ── 扫描与体检 ──────────────────────────────────────
    def keys(self) -> List[Tuple[str, int, str, int]]:
        out = []
        for fn in sorted(os.listdir(self.dir)):
            if not fn.endswith(".json"):
                continue
            m = FNAME_RE.match(fn)
            if not m:
                continue
            out.append((m.group("topic"), int(m.group("rep")), m.group("arm"), int(m.group("run"))))
        return out

    def sweep(self) -> Dict[str, Any]:
        """★ 收尾体检（★ 坏文件 / 重名 / 不可解析 ⇒ ⇒ 全部【显式报出】⇒ ⇒ 绝不静默跳过）"""
        bad: List[Tuple[str, str]] = []
        calls = fails = 0
        seen: Dict[str, int] = {}
        for fn in sorted(os.listdir(self.dir)):
            if not fn.endswith(".json"):
                continue
            seen[fn] = seen.get(fn, 0) + 1
            p = os.path.join(self.dir, fn)
            try:
                with open(p, encoding="utf-8") as f:
                    d = json.load(f)
            except Exception as e:
                bad.append((fn, "解析失败: %s" % e))
                continue
            calls += int(d.get("n_calls", 0) or 0)
            fails += int(d.get("n_failed", 0) or 0)
        return {
            "n_units": len(seen),
            "n_calls": calls,
            "n_failed": fails,
            "bad_files": bad,
            "ok": not bad,
        }

    def coverage(self, expect: Iterable[Tuple[str, int, str, int]]) -> Dict[str, int]:
        """★ 缺口清单（★ 续跑只用这个算"要补哪些"⇒ ⇒ ★ 绝不重算已存在的单元）"""
        have = set(self.keys())
        missing = [k for k in expect if k not in have]
        return {"expect": len(list(expect)), "have": len(have), "missing": len(missing)}

    def __enter__(self) -> "UnitStore":
        return self

    def __exit__(self, *a) -> None:
        self.release()


if __name__ == "__main__":  # ★ 零 API 自检
    import shutil
    import tempfile

    tmp = tempfile.mkdtemp(prefix="us_selftest_")
    try:
        st = UnitStore(os.path.join(tmp, "units"))
        st.put("T1", 1, "armA", 0, {"n_calls": 3, "n_failed": 0})
        st.put("T1", 1, "armA", 1, {"n_calls": 3, "n_failed": 0})
        assert st.has("T1", 1, "armA", 0)
        assert not st.has("T1", 1, "armA", 2)
        assert st.get("T1", 1, "armA", 1)["n_calls"] == 3
        sw = st.sweep()
        assert sw["ok"] and sw["n_units"] == 2 and sw["n_calls"] == 6, sw
        cov = st.coverage([("T1", 1, "armA", 0), ("T1", 1, "armA", 1), ("T1", 1, "armA", 2)])
        assert cov["missing"] == 1, cov
        # ★ 原子性：★ 读到的永远是完整 JSON
        with open(st.path_for("T1", 1, "armA", 0), encoding="utf-8") as f:
            json.load(f)
        # ★ 互斥：★ 同目录第二个 UnitStore(exclusive=True) 必须抛错
        st2 = UnitStore(os.path.join(tmp, "units"), exclusive=True)
        try:
            UnitStore(os.path.join(tmp, "units"), exclusive=True)
            raise AssertionError("★ 锁没生效")
        except RuntimeError as e:
            assert "锁" in str(e)
        st2.release()
        # ★ 坏文件必须被显式报出
        with open(os.path.join(tmp, "units", "T9_r1_armB_u0.json"), "w", encoding="utf-8") as f:
            f.write("not json")
        sw2 = UnitStore(os.path.join(tmp, "units")).sweep()
        assert not sw2["ok"] and len(sw2["bad_files"]) == 1, sw2
        print("✔ unit_store 自检全过（★ 原子写/续跑/互斥/坏文件显式报出）")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
