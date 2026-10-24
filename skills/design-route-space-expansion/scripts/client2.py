"""生成 + embedding 双通道（臂 3/臂 4 用）。
embedding 参数是 texts（不是 input）且必须带 type:db。
**529 过载要降级换模型；429 限流只退避不换模型**（换模型会改掉「模型构成」这个变量）。"""
import os, re, json, time, math, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = os.environ.get("OPENROUTER_BASE_URL", "https://api.minimaxi.com/v1")
KEY = os.environ.get("MINIMAX_SUBSCRIPTION_KEY", "")
MODELS = ["MiniMax-M3", "MiniMax-M3.1-Flash-Preview", "MiniMax-M2.7", "MiniMax-M2.5",
          "MiniMax-M2.1", "MiniMax-M2", "MiniMax-M2.7-highspeed",
          "MiniMax-M2.5-highspeed", "MiniMax-M2.1-highspeed"]
PRIMARY = os.environ.get("PRIMARY_MODEL", "MiniMax-M3")
FALLBACKS = ["MiniMax-M3.1-Flash-Preview", "MiniMax-M2.7"]
MODEL_LOG = {}


def _is_overload(t):
    t = t or ""
    return ("overloaded" in t) or ("负载较高" in t) or ('"529"' in t)


def st(t):
    t = re.sub(r"<think>.*?</think>", "", t or "", flags=re.S)
    return re.sub(r"^.*?</think>", "", t, flags=re.S).strip()


def chat(p, model=None, temp=1.0, mt=8000, tries=(12000, 16000), min_ok=300):
    """三种失败机制都要挡：
       1) M3.1-Flash 把思考放进 reasoning_content，content 可能整个缺失
       2) 弱模型档位会把预算全花在 meta 分析 persona 指令上，<think> 未闭合、无正文
       3) think 吃光预算导致 finish_reason='length' 截断
       4) **服务端过载 529** → 退避重试，仍不通则降级到健康档位
    """
    model = model or PRIMARY
    last = ""
    for mm in [model] + [m for m in FALLBACKS if m != model]:
        for m in (mt,) + tries:
            try:
                req = urllib.request.Request(f"{BASE}/chat/completions",
                    data=json.dumps({"model": mm, "messages": [{"role": "user", "content": p}],
                                    "temperature": temp, "max_tokens": m}).encode(),
                    headers={"Authorization": "Bearer " + KEY, "content-type": "application/json"})
                raw = urllib.request.urlopen(req, timeout=240).read().decode()
                if _is_overload(raw):
                    time.sleep(5)
                    break
                d = json.loads(raw)
                ch = d["choices"][0]
                last = ch["message"].get("content") or ""
                if ch.get("finish_reason") == "length":
                    continue
                o = st(last)
                if o.count("<think>") > o.count("</think>"):
                    continue
                if len(o) >= min_ok:
                    MODEL_LOG[mm] = MODEL_LOG.get(mm, 0) + 1
                    return o
            except urllib.error.HTTPError as e:
                body = ""
                try:
                    body = e.read().decode()
                except Exception:
                    pass
                if _is_overload(body):
                    time.sleep(5)
                    break
                time.sleep(2.5)
            except Exception:
                time.sleep(2.5)
    return last


def par(p, n, models=None, temp=1.0, mt=3000, workers=5):
    models = models or [PRIMARY] * n
    out = [""] * n
    with ThreadPoolExecutor(max_workers=workers) as ex:
        f = {ex.submit(chat, p, models[i], temp, mt): i for i in range(n)}
        for x in as_completed(f):
            try:
                out[f[x]] = x.result()
            except Exception:
                out[f[x]] = ""
    return out


_EMB = {}


def emb(texts, typ="db"):
    if not texts:
        return []
    req = urllib.request.Request(f"{BASE}/embeddings",
        data=json.dumps({"model": "embo-01", "type": typ, "texts": texts}).encode(),
        headers={"Authorization": "Bearer " + KEY, "content-type": "application/json"})
    for _ in range(3):
        try:
            v = json.loads(urllib.request.urlopen(req, timeout=90).read().decode())["vectors"]
            for t, e in zip(texts, v):
                _EMB[t] = e
            return v
        except Exception:
            time.sleep(2)
    return []


def cos(a, b):
    n = sum(x * y for x, y in zip(a, b))
    da = math.sqrt(sum(x * x for x in a))
    db = math.sqrt(sum(x * x for x in b))
    return n / (da * db) if da and db else 0.0
