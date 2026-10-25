#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ creativity-mechanism-skills · 仓级自检闸门 ★

============================================================
★ 为什么要有这个脚本（★ 2026-10-25 维护时发现 ★）
============================================================
★ 事件：★ 仓里 README 与 SKILL.md 都写着一个**并不存在**的脚本
★   `test_state_layer_rev3_mutations.py`，★ 而它被当成卖点宣传成
★   「★ 变异注入证明测试不是空转 ★」★★
★   ⇒ ★ 而真正带变异注入的是 `test_state_layer.py --self-test` ★
★   ⇒ ★ 而且那个 --self-test 在**发布后的布局**下【15 个变异全部构造失败】
★      （★ `_ROOT` 上溯层数算错 ★）⇒ ★ 也就是说这条能力【从来没在发布布局下跑过】★★
★
★ ⇒ ★ 教训：★ **"文档里写了"≠"仓里能跑"≠"读者照着能跑"** ★
★ ⇒ ★ 落法：★ 把自检做成【一个会红的脚本】★ ⇒ ★ 文档只指向它 ★★
============================================================

★ 本脚本的六项检查（★ 任何一项失败 ⇒ 非零退出 ★）
============================================================
  ① **清单双向核对**：★ SHA256SUMS.txt 里列的每个文件都要在、且哈希对上；
     ★ 仓里每个文件都要在清单里（★ 双向 ⇒ 漏列与过期都抓得到 ★）
  ② **重复文件逐字节一致**：★ scripts/ 与 scripts/creativity_lab/ 的同名副本
     （★ 维护时改一份忘一份 = 静默漂移 ★）
  ③ **引用完整性**：★ README 与各 SKILL.md 里提到的 `scripts/**` 与 `references/**`
     必须真实存在（★ 这次的 bug 就是这条 ★）
  ④ **README 自检命令逐条实跑**：★ 每条都要拿到【约定的退出码】★
  ⑤ **变异注入自检**：★ 层4 的 `--self-test` ⇒ ★ 证明"测试不是空转"★
  ⑥ **依赖可导入性**：★ 仓内【不依赖实验包】的脚本必须能 import ★

★ 零依赖、零网络、零额度（★ 只跑本地脚本 ★）
★ 用法：★ `python3 selfcheck.py`（★ 期望 exit 0 ★）
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
SKILLS = os.path.join(ROOT, "skills")

fails: list[str] = []
warns: list[str] = []
n_checks = 0


def sha256_file(p: str) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ok(msg: str) -> None:
    global n_checks
    n_checks += 1
    print("  ✔ %s" % msg)


def bad(msg: str) -> None:
    global n_checks
    n_checks += 1
    fails.append(msg)
    print("  ✘ %s" % msg)


def warn(msg: str) -> None:
    warns.append(msg)
    print("  ⚠️ %s" % msg)


def section(title: str) -> None:
    print()
    print("═══ %s ═══" % title)


# ────────────────────────────────────────────────────────────
# ① 清单双向核对
# ────────────────────────────────────────────────────────────
def check_manifest() -> None:
    section("① 清单双向核对（★ SHA256SUMS.txt ★）")
    man = os.path.join(ROOT, "SHA256SUMS.txt")
    if not os.path.exists(man):
        bad("缺 SHA256SUMS.txt ⇒ 交付方无法核验")
        return
    listed = {}
    for ln in open(man, encoding="utf-8").read().splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        parts = ln.split("  ", 1)
        if len(parts) != 2:
            parts = ln.split(" ", 1)
        if len(parts) != 2:
            warn("清单行格式异常（跳过）：%r" % ln)
            continue
        listed[parts[1].strip()] = parts[0].strip()

    # 仓内实际文件（★ 与清单同口径：★ git 跟踪的文件；★ 无 git 时退回文件系统遍历 ★）
    actual = set()
    _git = None
    try:
        import subprocess as _sp
        _r = _sp.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, timeout=60)
        if _r.returncode == 0 and _r.stdout.strip():
            _git = {x.strip() for x in _r.stdout.split("\n") if x.strip()}
    except Exception:
        _git = None
    if _git is not None:
        actual = {x for x in _git if x != "SHA256SUMS.txt"}
    else:
        for dirpath, dirnames, filenames in os.walk(ROOT):
            dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__")]
            for fn in filenames:
                rel = os.path.relpath(os.path.join(dirpath, fn), ROOT).replace(os.sep, "/")
                if rel == "SHA256SUMS.txt" or rel.endswith(".pyc"):
                    continue
                actual.add(rel)

    n_bad = n_miss = 0
    for rel, want in sorted(listed.items()):
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            n_miss += 1
            bad("清单列了但仓里没有：%s" % rel)
            continue
        got = sha256_file(p)
        if got != want:
            n_bad += 1
            bad("哈希不符：%s（清单 %s… 实际 %s…）" % (rel, want[:12], got[:12]))
    for rel in sorted(actual - set(listed)):
        bad("仓里有但清单没列：%s" % rel)
    if not n_bad and not n_miss and actual == set(listed):
        ok("清单双向一致：%d 个文件全部对上（★ 无漏列、无过期、无哈希不符 ★）" % len(listed))


# ────────────────────────────────────────────────────────────
# ② 重复文件逐字节一致
# ────────────────────────────────────────────────────────────
def check_duplicates() -> None:
    section("② 重复文件逐字节一致（★ 改一份忘一份 = 静默漂移 ★）")
    base = os.path.join(SKILLS, "state-driven-agent", "scripts")
    pairs = [("apply_state_layer_rev3.py",), ("test_state_layer.py",), ("unit_store.py",)]
    for (fn,) in pairs:
        a = os.path.join(base, fn)
        b = os.path.join(base, "creativity_lab", fn)
        if not (os.path.exists(a) and os.path.exists(b)):
            bad("重复对缺文件：%s" % fn)
            continue
        ha, hb = sha256_file(a), sha256_file(b)
        if ha == hb:
            ok("%s 两份副本逐字节一致（%s…）" % (fn, ha[:12]))
        else:
            bad("%s 两份副本【不一致】（%s… vs %s…）⇒ 维护时已漂移" % (fn, ha[:12], hb[:12]))
    # state_layer.py 是 shim（★ 故意不同 ★）⇒ 只确认它指向真实现
    shim = os.path.join(base, "state_layer.py")
    real = os.path.join(base, "creativity_lab", "state_layer.py")
    if os.path.exists(shim) and os.path.exists(real):
        txt = open(shim, encoding="utf-8").read()
        if "creativity_lab.state_layer" in txt:
            ok("state_layer.py 是指向真实现的 shim（★ 故意与副本不同 ★）")
        else:
            bad("state_layer.py 不再指向 creativity_lab.state_layer ⇒ shim 断了")


# ────────────────────────────────────────────────────────────
# ③ 引用完整性
# ────────────────────────────────────────────────────────────
def check_references() -> None:
    section("③ 引用完整性（★ 文档提到的文件必须存在 ★）")
    docs = [os.path.join(ROOT, "README.md")]
    for sk in sorted(os.listdir(SKILLS)) if os.path.isdir(SKILLS) else []:
        p = os.path.join(SKILLS, sk, "SKILL.md")
        if os.path.exists(p):
            docs.append(p)
    pat = re.compile(r"`((?:skills/)?[A-Za-z0-9_./-]+\.(?:py|md|json|txt|docx))`")
    # ★ 泛指名（★ 不是对某个具体文件的引用 ★）⇒ 不查
    _GENERIC = {"SKILL.md", "README.md", "LICENSE", "PROTOCOL.md", "DEV-SPEC.md"}
    n_ref = 0
    for d in docs:
        txt = open(d, encoding="utf-8").read()
        ddir = os.path.dirname(d)          # ★ 文档所在目录（★ SKILL.md 里的相对路径是相对它的 ★）
        for m in pat.finditer(txt):
            ref = m.group(1)
            # 只查仓内相对引用（★ 绝对路径 / URL 不查 ★）
            if ref.startswith(("http", "/")):
                continue
            # ★ 候选：★ 文档同级 ★ / 该 skill 的 scripts/ ★ references/ ★ 仓根 ★
            #   ★ SKILL.md 的标准布局是 scripts/ + references/ ★ ⇒ 文档里写 `space.py`
            #   ★ 指的是 scripts/space.py ★ ⇒ 必须按布局解析（★ 否则全是误报 ★）★
            _tail = ref.split("/", 1)[1] if ref.startswith("skills/") else ref
            cands = [os.path.join(ddir, ref),
                     os.path.join(ddir, "scripts", ref),
                     os.path.join(ddir, "references", ref),
                     os.path.join(ddir, "scripts", _tail),
                     os.path.join(ddir, "references", _tail),
                     os.path.join(ROOT, ref),
                     os.path.join(ROOT, _tail)]
            # ★ README 的「目录」段会列【任意 skill 的 scripts/ 下】的文件名 ⇒ 也试一遍 ★
            if os.path.isdir(SKILLS):
                for sk in os.listdir(SKILLS):
                    for sub in ("scripts", "references"):
                        cands.append(os.path.join(SKILLS, sk, sub, _tail))
                        cands.append(os.path.join(SKILLS, sk, sub, ref))
            if ref in _GENERIC:
                continue
            if not any(os.path.exists(c) for c in cands):
                n_ref += 1
                bad("%s 引用了不存在的文件：%s"
                    % (os.path.relpath(d, ROOT), ref))
    if n_ref == 0:
        ok("所有文档里的仓内文件引用都存在（★ %d 份文档 ★）" % len(docs))


# ────────────────────────────────────────────────────────────
# ④⑤⑥ 命令实跑
# ────────────────────────────────────────────────────────────
def run(label: str, argv, cwd=None, expect_rc=0, must_contain=None, timeout=300):
    try:
        r = subprocess.run(argv, cwd=cwd or ROOT, capture_output=True, text=True,
                           timeout=timeout)
    except subprocess.TimeoutExpired:
        bad("%s ⇒ 超时（%ds）" % (label, timeout))
        return None
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode != expect_rc:
        bad("%s ⇒ 退出码 %d（★ 期望 %d ★）\n     %s"
            % (label, r.returncode, expect_rc, out.strip()[-300:]))
        return out
    if must_contain and must_contain not in out:
        bad("%s ⇒ 退出码对，但输出里没有 %r\n     %s"
            % (label, must_contain, out.strip()[-300:]))
        return out
    ok("%s ⇒ exit=%d" % (label, r.returncode))
    return out


def check_commands() -> None:
    section("④ README 自检命令逐条实跑（★ 退出码必须对 ★）")
    l3 = os.path.join(SKILLS, "learning-route-generalization", "scripts")
    l4 = os.path.join(SKILLS, "state-driven-agent", "scripts")
    l2 = os.path.join(SKILLS, "design-route-space-expansion", "scripts")

    run("层3 import 自检（space + metrics_priorart）",
        [PY, "-c", "import sys; sys.path.insert(0, %r); import space, metrics_priorart; print('ok')" % l3],
        expect_rc=0, must_contain="ok")

    run("层3 条件从句扫描", [PY, os.path.join(l3, "condition_clause_scan.py")], expect_rc=0)
    run("层3 族键重算", [PY, os.path.join(l3, "family_recompute.py")], expect_rc=0)
    run("层3 嵌套校准自检", [PY, os.path.join(l3, "nested_calib_self.py")], expect_rc=0)

    run("层4 状态层规格测试（8 项）", [PY, os.path.join(l4, "test_state_layer.py")],
        expect_rc=0, must_contain="全部通过")

    section("⑤ 变异注入自检（★ 证明测试不是空转 ★）")
    out = run("层4 变异注入（--self-test）",
              [PY, os.path.join(l4, "test_state_layer.py"), "--self-test"],
              expect_rc=0, must_contain="全部如期失败")
    if out and "全部如期失败" in out:
        m = re.search(r"变异注入自检：(\d+)/(\d+) 项", out)
        if m and m.group(1) == m.group(2) and int(m.group(2)) > 0:
            ok("变异 %s 项【全部如期失败】⇒ 测试是活的" % m.group(1))
        elif m:
            bad("变异 %s/%s ⇒ 有变异没被抓住 ⇒ 测试有恒真项" % (m.group(1), m.group(2)))

    section("⑥ 依赖可导入性（★ 不依赖实验包的脚本必须能 import ★）")
    for name in ("arm3", "shared", "topics4", "client", "client2"):
        run("层2 %s 可 import" % name, [PY, "-c", "import %s" % name], cwd=l2, expect_rc=0)
    run("层3 family_output_real 可 import（★ 族键口径改用本仓同口径实现 ★）",
        [PY, "-c", "import family_output_real"], cwd=l3, expect_rc=0)
    run("层4 creativity_lab 可 import",
        [PY, "-c", "import creativity_lab.state_layer"], cwd=l4, expect_rc=0)
    # 依赖实验包的三个脚本 ⇒ 期望【响亮失败 + 可执行提示】（★ 不是静默通过 ★）
    for name in ("dual", "adhd_repro", "run_compare5"):
        r = subprocess.run([PY, "-c", "import %s" % name], cwd=l2,
                           capture_output=True, text=True, timeout=120)
        if r.returncode == 0:
            bad("层2 %s 在缺实验包时竟然 import 成功 ⇒ 依赖声明与实际不符" % name)
        elif "PYTHONPATH" not in (r.stdout + r.stderr):
            bad("层2 %s 缺依赖时报的是裸错误（★ 没有可执行提示 ★）" % name)
        else:
            ok("层2 %s 缺依赖时【响亮失败 + 给可执行提示】" % name)


def main() -> int:
    print("=" * 62)
    print("creativity-mechanism-skills · 仓级自检闸门")
    print("仓根：%s" % ROOT)
    print("=" * 62)
    check_manifest()
    check_duplicates()
    check_references()
    check_commands()
    print()
    print("=" * 62)
    if warns:
        print("⚠️ %d 条告警（不判失败）：" % len(warns))
        for w in warns:
            print("   - %s" % w)
    if fails:
        print("❌ %d 项失败（★ 检查项 %d ★）：" % (len(fails), n_checks))
        for f in fails:
            print("   - %s" % f)
        print("=" * 62)
        return 1
    print("✅ 自检全绿：%d 项检查通过" % n_checks)
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
