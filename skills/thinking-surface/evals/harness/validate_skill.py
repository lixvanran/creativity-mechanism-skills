"""Agent Skills 规范符合性检查（依据 agentskills.io/specification 的公开约束）。

自研校验器（环境里没有 skills-ref），检查项：
  S1  SKILL.md 存在于 skill 根
  S2  frontmatter 存在且能解析
  S3  name 合法：1-64 字符；仅小写字母/数字/连字符；不以连字符开头结尾；无连续连字符；与目录名一致
  S4  description 合法：1-1024 字符、非空、含"何时用"的触发线索
  S5  SKILL.md 行数 < 500
  S6  SKILL.md 估算 token < 5000
  S7  references/ 只深一层（无嵌套子目录）
  S8  SKILL.md 里引用的相对路径都真实存在
  S9  scripts/ 里的脚本可编译（python 文件用 compile() 检查语法）

退出码 0 全过 / 1 有红。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


def estimate_tokens(text: str) -> int:
    """粗估 token：中文 1 字≈1 token，ASCII 4 字符≈1 token。"""
    cjk = len(re.findall(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]", text))
    other = len(text) - cjk
    return int(cjk + other / 4)


def parse_frontmatter(md: str):
    if not md.startswith("---"):
        return None, md
    end = md.find("\n---", 3)
    if end == -1:
        return None, md
    block = md[3:end]
    body = md[end + 4:]
    fm = {}
    key = None
    for line in block.splitlines():
        if not line.strip():
            continue
        if re.match(r"^\s*[A-Za-z_-]+\s*:", line) and not line.startswith(" "):
            k, v = line.split(":", 1)
            key = k.strip()
            fm[key] = v.strip()
        elif key:
            fm[key] = (fm[key] + " " + line.strip()).strip()
    return fm, body


def validate(root: Path) -> list[str]:
    errs: list[str] = []
    skill_md = root / "SKILL.md"
    if not skill_md.exists():
        return [f"S1 缺 SKILL.md：{root}"]
    md = skill_md.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(md)
    if fm is None:
        return ["S2 frontmatter 缺失或格式不对（应以 --- 开头并以 --- 结束）"]

    name = fm.get("name", "")
    desc = fm.get("description", "")
    if not (1 <= len(name) <= 64):
        errs.append(f"S3 name 长度 {len(name)} 不在 1-64")
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name):
        errs.append(f"S3 name 非法字符/连续连字符/首尾连字符：{name!r}")
    if name != root.name:
        errs.append(f"S3 name({name!r}) 必须与目录名({root.name!r})一致")
    if not (1 <= len(desc) <= 1024):
        errs.append(f"S4 description 长度 {len(desc)} 不在 1-1024")
    if not re.search(r"(当|用于|适用于|use when|when )", desc, re.I):
        errs.append("S4 description 必须说明「何时用」（缺触发线索）")
    if not re.search(r"(用于|use|extraction|analys|design|扩|生成|转换|检查|验证|审计)", desc, re.I):
        errs.append("S4 description 必须说明「做什么」")

    lines = body.splitlines()
    if len(lines) >= 500:
        errs.append(f"S5 SKILL.md {len(lines)} 行，应 < 500")
    tok = estimate_tokens(body)
    if tok >= 5000:
        errs.append(f"S6 SKILL.md 估算 {tok} token，应 < 5000")

    refs = root / "references"
    if refs.exists():
        for d in refs.iterdir():
            if d.is_dir():
                errs.append(f"S7 references/ 下不允许嵌套目录：{d.name}/")

    for m in re.finditer(r"`((?:references|scripts|assets|evals)/[A-Za-z0-9_\-./]+)`", body):
        rel = m.group(1)
        if not (root / rel).exists():
            errs.append(f"S8 SKILL.md 引用了不存在的文件：{rel}")
    for m in re.finditer(r"\[[^\]]*\]\(([^)]+)\)", body):
        rel = m.group(1)
        if rel.startswith("http"):
            continue
        if not (root / rel).exists():
            errs.append(f"S8 SKILL.md 链接了不存在的文件：{rel}")

    scripts = root / "scripts"
    if scripts.exists():
        for f in scripts.glob("*.py"):
            try:
                compile(f.read_text(encoding="utf-8"), str(f), "exec")
            except SyntaxError as e:
                errs.append(f"S9 脚本语法错误 {f.name}: {e}")

    return errs


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "../skill/thinking-surface").resolve()
    errs = validate(root)
    if errs:
        print(f"FAIL: {root} —— {len(errs)} 项不合规")
        for e in errs:
            print("  -", e)
        return 1
    md = (root / "SKILL.md").read_text(encoding="utf-8")
    fm, body = parse_frontmatter(md)
    print(f"OK: {root.name} 符合 Agent Skills 规范")
    print(f"  name={fm.get('name')}  desc={len(fm.get('description',''))} 字符")
    print(f"  SKILL.md {len(body.splitlines())} 行 / 估算 {estimate_tokens(body)} token")
    return 0


if __name__ == "__main__":
    sys.exit(main())
