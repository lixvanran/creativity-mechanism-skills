"""MiniMax 双通道客户端（带过载降级）。
补丁要点：**529 过载**要降级换模型，**429 限流**只退避不换模型
（换模型会悄悄改掉「模型构成」这个变量，臂间对比就失效了）。"""
from __future__ import annotations
import json, os, re, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

BASE = os.environ.get("OPENROUTER_BASE_URL", "https://api.minimaxi.com/v1").rstrip("/")
_KEY = os.environ.get("MINIMAX_SUBSCRIPTION_KEY", "")
MODELS = ["MiniMax-M3", "MiniMax-M3.1-Flash-Preview", "MiniMax-M2.7", "MiniMax-M2.5",
          "MiniMax-M2.1", "MiniMax-M2", "MiniMax-M2.7-highspeed",
          "MiniMax-M2.5-highspeed", "MiniMax-M2.1-highspeed"]
PRIMARY = os.environ.get("PRIMARY_MODEL", "MiniMax-M3")
FALLBACKS = ["MiniMax-M3.1-Flash-Preview", "MiniMax-M2.7"]


def _is_overload(txt: str) -> bool:
    t = txt or ""
    return ("overloaded" in t) or ("负载较高" in t) or ('"529"' in t)


_T1 = re.compile(r"<think>.*?</think>", re.S)
_T2 = re.compile(r"^.*?</think>", re.S)


def strip_think(raw: str) -> str:
    return _T2.sub("", _T1.sub("", raw or "")).strip()


@dataclass
class Call:
    model: str
    purpose: str
    max_tokens: int
    finish_reason: str = ""
    content_len: int = 0
    ok: bool = False
    secs: float = 0.0
    err: str = ""


class LLM:
    def __init__(self, recorder: list | None = None):
        self.rec = recorder if recorder is not None else []

    def _post(self, url: str, payload: dict, timeout: int = 240):
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {_KEY}", "content-type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode())

    def chat(self, prompt: str, *, model: str = "", temp: float = 1.0,
             max_tokens: int = 8000, budgets=(12000, 16000), min_ok: int = 200,
             purpose: str = "") -> str:
        model = model or PRIMARY
        last = ""
        t0 = time.time()
        for mm in [model] + [m for m in FALLBACKS if m != model]:
            overload_hits = 0
            for mt in (max_tokens,) + tuple(budgets):
                try:
                    d = self._post(f"{BASE}/chat/completions", {
                        "model": mm, "messages": [{"role": "user", "content": prompt}],
                        "temperature": temp, "max_tokens": mt})
                    ch = d["choices"][0]
                    last = strip_think(ch["message"].get("content") or "")
                    fr = ch.get("finish_reason", "")
                    self.rec.append(Call(mm, purpose, mt, fr, len(last), False, time.time() - t0))
                    if fr == "length":
                        continue
                    if last.count("<think>") > last.count("</think>"):
                        continue
                    if len(last) >= min_ok:
                        self.rec[-1].ok = True
                        return last
                except urllib.error.HTTPError as e:
                    body = ""
                    try:
                        body = e.read().decode()
                    except Exception:
                        pass
                    if _is_overload(body):
                        overload_hits += 1
                        time.sleep(5 + 4 * overload_hits)
                        break
                    time.sleep(2.5)
                except Exception:
                    time.sleep(2.5)
        return last

    def chat_many(self, prompts: list[str], *, workers: int = 3, **kw) -> list[str]:
        if workers <= 1:
            return [self.chat(p, **kw) for p in prompts]
        out = [""] * len(prompts)
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(self.chat, p, **kw): i for i, p in enumerate(prompts)}
            for f in as_completed(futs):
                try:
                    out[futs[f]] = f.result()
                except Exception:
                    out[futs[f]] = ""
        return out

    _cache: dict = {}

    def embed(self, texts: list[str], typ: str = "db") -> list[list[float]]:
        """MiniMax embo-01。参数是 texts + type:'db'（不是 input/embed_type）。"""
        miss = [t for t in texts if t not in self._cache]
        for i in range(0, len(miss), 32):
            chunk = miss[i:i + 32]
            d = self._post(f"{BASE}/embeddings",
                           {"model": "embo-01", "type": typ, "texts": chunk})
            for t, v in zip(chunk, d["vectors"]):
                self._cache[t] = v
        return [self._cache[t] for t in texts]


def cosine(a, b) -> float:
    if a is None or b is None:
        return 0.0
    try:
        import numpy as _np
        A = _np.asarray(a, dtype=float).ravel()
        B = _np.asarray(b, dtype=float).ravel()
    except Exception:
        return 0.0
    if A.size == 0 or B.size == 0 or A.size != B.size:
        return 0.0
    n = float(A @ B)
    na = float(_np.linalg.norm(A))
    nb = float(_np.linalg.norm(B))
    return n / (na * nb) if na and nb else 0.0
