"""度量层。

三条硬纪律：
1. **不把 n 放进分母**（有效秩/n、有效秩随 n 下降是恒等式，不是因变量）⇒ 模态数一律用绝对值，
   且只在【同 n】的臂之间比较（n=3 统一子集）。
2. **宽度必须配有效性**（一派胡言也能拿高宽度）⇒ 宽度指标一律与兑现率并排报告。
3. **失败不静默归零** ⇒ 任何解析失败/空产出单列计数，读数里显示 N，不显示 0。
"""
from __future__ import annotations

import json
import math
import re
from itertools import combinations

from sklearn.cluster import AgglomerativeClustering
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# —— 预注册的参数（改任何一项都必须同步改 prereg.md 并重跑）——
CLUSTER_DISTANCE = 0.35  # 平均连接层次聚类的距离阈值
SVD_DIM = 8
MATCHED_N = 3  # 跨臂比较时统一截取的样本数
COVERAGE_HIT_RATIO = 2 / 3  # 一条轴被覆盖所需的 must 命中比例
NEG_MARKERS = ("综合", "多角度", "换个角度", "全方位", "各种方式", "既要", "也要")


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def axis_hits(axis, text: str) -> dict:
    """一条轴在一条文本上的机械命中情况。"""
    t = _norm(text)
    must = axis.get("must", []) or []
    forbid = axis.get("forbid", []) or []
    hit_must = [w for w in must if w and w in t]
    hit_forbid = [w for w in forbid if w and w in t]
    need = math.ceil(len(must) * COVERAGE_HIT_RATIO) if must else 0
    covered = (len(hit_must) >= need) and (len(hit_forbid) == 0)
    return {
        "axis": axis["id"],
        "hit_must": hit_must,
        "hit_forbid": hit_forbid,
        "need": need,
        "covered": covered,
    }


def coverage_union(axes, texts) -> dict:
    """一组文本对一组轴的覆盖（并集口径：这组文本合起来覆盖了几条轴）。"""
    per_axis = {}
    covered = 0
    for a in axes:
        res = [axis_hits(a, t) for t in texts]
        ok = any(r["covered"] for r in res)
        per_axis[a["id"]] = {
            "covered": ok,
            "hit_must_any": sorted({w for r in res for w in r["hit_must"]}),
            "hit_forbid_any": sorted({w for r in res for w in r["hit_forbid"]}),
        }
        covered += int(ok)
    return {"n_covered": covered, "n_axes": len(axes), "per_axis": per_axis}


def neg_marker_rate(text: str) -> float:
    """「我要换个角度」这类表演性表述的出现率（每千字）。"""
    n = max(1, len(text or ""))
    t = _norm(text)
    return sum(t.count(m) for m in NEG_MARKERS) * 1000.0 / n


_SECTION_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:\*\*)?(?:方案|思路|方式|路径|做法|角度)\s*"
    r"([一二三四五六七八九十1-9])\s*(?:[、.．)）:：]|\*\*)?",
    re.M,
)
_LOOSE_SECTION_RE = re.compile(r"^\s*(?:#{1,6}\s*)?(?:\*\*)?([一二三四五六七八九十1-9])\s*[、.．)）]", re.M)
_SUMMARY_RE = re.compile(r"(综合|总结|以上|最终|合起来|归纳|整体来看)")


def _trim_summary(seg: str) -> str:
    """段内若出现「综合/总结」类标题，从那里截断——综合作废：它不是一条独立思路。"""
    m = _SUMMARY_RE.search(seg)
    if m and m.start() > 0:
        return seg[: m.start()].strip()
    return seg


def split_ideas(text: str, min_len: int = 60, strict: bool = True):
    """把一段回答切成「单条思路」。

    为什么需要它：不同臂的「思路条数」不同——多分支臂一次输出 1 条，
    而「一次要 4 个方案」的臂一次输出 4 条。若直接按整段量覆盖，
    长答案天然覆盖更多轴，覆盖数就成了长度的代理而不是思维面的度量。
    ⇒ 统一到「单条思路」粒度，跨臂才可比。

    strict=True：只认「方案一/思路二」这类**语义小标题**（用于还原 A2 的 4 条思路）
    strict=False：连「1. 2. 3.」这种普通编号也认（只做诊断：看某个"单方案"臂
                  是否偷偷在一条输出里塞了多条思路）

    返回 (units, note)；note 记录切分是否成功（失败时退回整段，调用方须记账）。
    """
    t = (text or "").strip()
    if not t:
        return [], "empty"
    rx = _SECTION_RE if strict else _LOOSE_SECTION_RE
    marks = list(rx.finditer(t))
    if len(marks) < 2:
        return [t], "unsplit"
    units = []
    for i, m in enumerate(marks):
        start = m.start()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(t)
        seg = _trim_summary(t[start:end].strip())
        if len(seg) < min_len:
            continue
        units.append(seg)
    if len(units) < 2:
        return [t], "unsplit"
    return units, "split"


def _char_tokens(s: str) -> list[str]:
    s = re.sub(r"\s+", "", s or "")
    s = re.sub(r"[，。！？；：、,.!?;:\-—…·「」『』（）()\[\]{}\"'`~@#$%^&*+=|<>/\\]+", " ", s)
    out = []
    for chunk in s.split(" "):
        if not chunk:
            continue
        out.append(chunk)
        for i in range(len(chunk) - 1):
            out.append(chunk[i : i + 2])
    return out


def modality_count(texts) -> int:
    """文本集合的模态数（聚类簇数，绝对值）。文本少于 2 时无意义。"""
    texts = [t for t in texts if (t or "").strip()]
    n = len(texts)
    if n < 2:
        return 1 if n == 1 else 0
    vec = TfidfVectorizer(tokenizer=_char_tokens, analyzer="word", token_pattern=None, lowercase=False)
    X = vec.fit_transform(texts)
    k = min(SVD_DIM, max(1, X.shape[1] - 1), n - 1)
    if k >= 2:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            Z = TruncatedSVD(n_components=k, random_state=0).fit_transform(X)
    else:
        Z = X.toarray()
    D = 1.0 - cosine_similarity(Z)
    np_ = D.shape[0]
    if np_ < 2:
        return 1
    cl = AgglomerativeClustering(n_clusters=None, distance_threshold=CLUSTER_DISTANCE, linkage="average", metric="precomputed")
    cl.fit(D)
    return int(len(set(cl.labels_)))


def skeleton_distance(skeletons) -> float:
    """机制骨架的平均两两 Jaccard 距离（借 RPD 的 step-level 语义距离思路）。

    skeletons: list[list[str]]，每个是一个方案的核心机制短语列表。
    返回 0-1，越大表示两两做法越不同。少于 2 个样本时返回 nan（不静默填 0）。
    """
    sks = [set(s or []) for s in skeletons]
    sks = [s for s in sks if s]
    if len(sks) < 2:
        return float("nan")
    ds = []
    for a, b in combinations(sks, 2):
        inter = len(a & b)
        union = len(a | b)
        ds.append(1.0 - (inter / union if union else 1.0))
    return sum(ds) / len(ds)


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b) if (a | b) else 1.0


def summarize(values):
    """一组读数的均值/标准差/方向计数。空集显式返回 None，不假装是 0。"""
    vals = [v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]
    if not vals:
        return {"n": 0, "mean": None, "sd": None, "min": None, "max": None}
    m = sum(vals) / len(vals)
    sd = math.sqrt(sum((v - m) ** 2 for v in vals) / (len(vals) - 1)) if len(vals) > 1 else 0.0
    return {"n": len(vals), "mean": m, "sd": sd, "min": min(vals), "max": max(vals)}


def sign_agreement(diffs) -> dict:
    """方向一致性：正/负/零各多少。判决线要用「≥2/3 题同向」。"""
    pos = sum(1 for d in diffs if d is not None and d > 0)
    neg = sum(1 for d in diffs if d is not None and d < 0)
    zero = sum(1 for d in diffs if d is not None and d == 0)
    return {"pos": pos, "neg": neg, "zero": zero, "n": len(diffs)}


def count_sections(text: str, strict: bool = True) -> int:
    """诊断用：数一��输出里有几个「分节」。不切内容，只数标题。

    用途：看某个「单方案」臂的一条输出里是不是偷偷塞了多条思路
    （那样它的覆盖会被高估）——纯诊断，不参与任何主指标。
    """
    rx = _SECTION_RE if strict else _LOOSE_SECTION_RE
    return len(list(rx.finditer(text or "")))
