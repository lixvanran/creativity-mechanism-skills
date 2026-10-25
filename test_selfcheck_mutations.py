#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ selfcheck.py 的变异注入自测（★ 证明【自检闸门本身】是活的 ★）

============================================================
★ 为什么要有这个脚本
============================================================
★ 纪律：★ **检查项必须先证明它会红** ⇒ ★ 否则一个恒真的检查项
★   （★ 「全绿」⇒ ★ 什么都能过 ★）比没有检查更危险 ★
★ ⇒ ★ 本脚本对 `selfcheck.py` 的每一类检查各注入一次变异 ⇒ ★
★   每次都必须【变红】且【报出正确的错因】⇒ ★ 否则说明那一类检查抓不到东西 ★
★
★ 做法：★ 把仓整体复制到临时目录 ⇒ ★ 在副本上变异 ⇒ ★ 跑副本里的 selfcheck ★
★   ⇒ ★ **绝不动真仓**（★ 破坏性操作只发生在副本 ★）
============================================================

★ 用法：★ `python3 test_selfcheck_mutations.py`（★ 期望 exit 0 ★）
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def copy_repo(dst: str) -> str:
    """★ 连 .git 一起复制（★ 让副本里的 git ls-files 可用 ★ ⇒ 与真仓同口径 ★）"""
    shutil.copytree(HERE, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return dst


def run_selfcheck(repo: str, timeout: int = 900):
    r = subprocess.run([PY, os.path.join(repo, "selfcheck.py")],
                       cwd=repo, capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def edit(path: str, old: str, new: str) -> None:
    s = io.open(path, encoding="utf-8").read()
    assert s.count(old) == 1, "定位失败 count=%d in %s" % (s.count(old), path)
    io.open(path, "w", encoding="utf-8").write(s.replace(old, new))


# ── 变异清单：★ (标签, 施加函数, 必须出现的错因关键字) ★
def m_hash_mismatch(repo):
    p = os.path.join(repo, "skills/learning-route-generalization/scripts/space.py")
    s = io.open(p, encoding="utf-8").read()
    io.open(p, "w", encoding="utf-8").write(s + "\n# ★ 变异：改内容 ⇒ 清单哈希必须变红 ★\n")


def m_manifest_stale(repo):
    os.remove(os.path.join(repo, "skills/state-driven-agent/scripts/unit_store.py"))


def m_manifest_missing_entry(repo):
    p = os.path.join(repo, "skills/state-driven-agent/scripts/brand_new_file.py")
    io.open(p, "w", encoding="utf-8").write("# ★ 变异：仓里有、清单没列 ★\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, capture_output=True, timeout=120)
    subprocess.run(["git", "-c", "user.email=m@x", "-c", "user.name=m", "commit",
                    "-q", "-m", "mut: new file"], cwd=repo, capture_output=True, timeout=120)


def m_duplicate_drift(repo):
    p = os.path.join(repo, "skills/state-driven-agent/scripts/creativity_lab/unit_store.py")
    s = io.open(p, encoding="utf-8").read()
    io.open(p, "w", encoding="utf-8").write(s + "\n# ★ 变异：副本漂移 ★\n")


def m_bad_reference(repo):
    p = os.path.join(repo, "README.md")
    s = io.open(p, encoding="utf-8").read()
    io.open(p, "w", encoding="utf-8").write(s + "\n`zzz_definitely_missing_xyz.py`\n")


def m_broken_import(repo):
    p = os.path.join(repo, "skills/learning-route-generalization/scripts/space.py")
    s = io.open(p, encoding="utf-8").read()
    io.open(p, "w", encoding="utf-8").write("def broken(:\n" + s)


def m_neuter_mutation_test(repo):
    """★ 变异注入自测本身被阉割 ⇒ ⑤ 块必须红（★ 防止"假绿" ★）"""
    p = os.path.join(repo, "skills/state-driven-agent/scripts/test_state_layer.py")
    edit(p, "for mut_name, old, new, target_test, why in MUTATIONS:",
         "for mut_name, old, new, target_test, why in []:  # ★ 变异：阉割变异注入 ★")


def m_silent_missing_dep(repo):
    """★ 缺依赖时【报裸错误、没给可执行提示】⇒ ⑥ 块必须红（★ fail-open / 提示丢失检测 ★）"""
    p = os.path.join(repo, "skills/design-route-space-expansion/scripts/_deps.py")
    s = io.open(p, encoding="utf-8").read()
    # ★ 把 require() 的"响亮失败"改成"静默放行"⇒ 后续 import 只会报裸 ModuleNotFoundError ★
    marker = "def require("
    assert marker in s
    i = s.index(marker)
    j = s.index("\n", s.index(":", i))
    s = s[:j + 1] + "    return None  # ★ 变异：静默放行 ★\n" + s[j + 1:]
    io.open(p, "w", encoding="utf-8").write(s)


MUTATIONS = [
    ("M1 清单哈希不符", m_hash_mismatch, "哈希不符"),
    ("M2 清单列了但文件没了", m_manifest_stale, "清单列了但仓里没有"),
    ("M3 仓里有但清单没列", m_manifest_missing_entry, "仓里有但清单没列"),
    ("M4 重复副本漂移", m_duplicate_drift, "两份副本"),
    ("M5 文档引用不存在文件", m_bad_reference, "引用了不存在的文件"),
    ("M6 模块语法坏 ⇒ import 失败", m_broken_import, "层3 import 自检"),
    ("M7 变异注入自测被阉割", m_neuter_mutation_test, "变异"),
    ("M8 缺依赖静默放行（提示丢失）", m_silent_missing_dep, "裸错误"),
]


def main() -> int:
    print("=" * 62)
    print("selfcheck.py · 变异注入自测")
    print("=" * 62)
    tmp = tempfile.mkdtemp(prefix="selfcheck_mut_")
    fails = []
    try:
        # ★ 基线：★ 未变异的副本必须全绿（★ 否则下面的"变红"没有意义 ★）
        base = os.path.join(tmp, "baseline")
        copy_repo(base)
        rc, out = run_selfcheck(base)
        if rc != 0:
            print("✘ 基线就不绿（exit=%d）⇒ 变异测试的前提不成立" % rc)
            print(out[-1500:])
            return 2
        print("✔ 基线全绿（exit=0）⇒ 下面每次变异都必须让它【变红】")

        for tag, fn, expect in MUTATIONS:
            d = os.path.join(tmp, tag.split()[0])
            copy_repo(d)
            try:
                fn(d)
            except Exception as e:
                print("  ✘ %s ⇒ 变异本身没施加成功：%s" % (tag, e))
                fails.append(tag)
                continue
            rc, out = run_selfcheck(d)
            if rc == 0:
                print("  ✘ %s ⇒ ★ 仍然全绿 ⇒ 这一类检查抓不到东西 ★" % tag)
                fails.append(tag)
            elif expect not in out:
                print("  ✘ %s ⇒ 变红了，但【错因不对】（期望 %r）" % (tag, expect))
                print("     " + out.strip()[-400:].replace("\n", "\n     "))
                fails.append(tag)
            else:
                print("  ✔ %s ⇒ 变红且错因正确（exit=%d）" % (tag, rc))
            shutil.rmtree(d, ignore_errors=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if fails:
        print("❌ %d/%d 项变异没被抓住" % (len(fails), len(MUTATIONS)))
        for f in fails:
            print("   - %s" % f)
        return 1
    print("✅ 全部 %d 项变异均被抓住 ⇒ selfcheck.py 的检查项是活的" % len(MUTATIONS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
