# -*- coding: utf-8 -*-
"""openrouter_client.py —— OpenRouter 通道（★ 与 client.py 同构、★ 同纪律 ★）

★ 为什么加这条通道：★ MiniMax Token Plan 额度/速率双限（429 / 2056 用量上限）★
★ ⇒ 路 B 与跨模型采样改走这里（★ 顺带满足「跨模型断言必须跨模型采样」★）
★ 纪律同源：★ 失败不静默归零（★ ok=False + failure_kind ★）｜凭据只走 header
"""
from __future__ import annotations
import json, os, random, re, time, urllib.error, urllib.request

BASE = "https://openrouter.ai/api/v1/chat/completions"
_KEY = os.environ.get("OPENROUTER_API_KEY", "")
if not _KEY:
    raise RuntimeError("OPENROUTER_API_KEY 未设置：拒绝在没有凭据的情况下假装跑实验")
_THINK_RE = re.compile(r"<think>.*?</think>", re.S)


def strip_think(text):
    return _THINK_RE.sub("", text or "").strip()


def chat(messages, model: str = "anthropic/claude-sonnet-4", temperature: float = 0.7,
         max_tokens: int = 1600, timeout: int = 240, retries: int = 3, extra: dict | None = None):
    body = {"model": model, "messages": messages, "temperature": temperature,
            "max_tokens": max_tokens}
    if extra:
        body.update(extra)
    last = ""
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(
                BASE, data=json.dumps(body).encode("utf-8"),
                headers={"Authorization": "Bearer " + _KEY,
                         "Content-Type": "application/json",
                         "HTTP-Referer": "https://github.com/lixvanran/creativity-mechanism-skills",
                         "X-Title": "thinking-surface-eval"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                d = json.loads(resp.read().decode("utf-8"))
            ch = (d.get("choices") or [{}])[0]
            raw = ((ch.get("message") or {}).get("content")) or ""
            text = strip_think(raw)
            usage = d.get("usage") or {}
            if not text:
                last = "empty_after_strip_think"
            else:
                return {"ok": True, "text": text, "usage": usage,
                        "finish_reason": ch.get("finish_reason"),
                        "model": d.get("model") or model}
        except urllib.error.HTTPError as e:
            body_txt = ""
            try:
                body_txt = e.read().decode("utf-8")[:200]
            except Exception:
                pass
            last = "HTTP%d:%s" % (e.code, body_txt)
            if e.code in (429, 500, 502, 503, 529):
                time.sleep(2.0 * (attempt + 1) + random.random() * 2)
                continue
            return {"ok": False, "text": "", "usage": {}, "failure_kind": "http_error",
                    "error": last, "model": model}
        except Exception as e:
            last = "%s: %s" % (type(e).__name__, str(e)[:120])
            time.sleep(2.0 * (attempt + 1))
    return {"ok": False, "text": "", "usage": {}, "failure_kind": "transport_error",
            "error": last, "model": model}


def json_call(messages, model: str = "anthropic/claude-sonnet-4", temperature: float = 0.0,
              max_tokens: int = 1200, retries: int = 2, extra: dict | None = None,
              thinking: str | None = None, schema_hint: str = ""):
    """★ thinking / schema_hint：★ 为与 client.py【同签名】而设、★ OpenRouter 侧忽略
    ★ （OpenRouter 没有 MiniMax 那种 thinking 开关；★ 需要关思考时用 extra={"reasoning":{"effort":"none"}} ★）"""
    """★ 判官/规划类：★ 关思考（★ 避免思考 token 吃光预算 ★）★ 解析失败显式记录 ★"""
    sys_msg = "You must answer with a single valid JSON object and nothing else."
    body = {"model": model, "messages": [{"role": "system", "content": sys_msg}] + list(messages),
            "temperature": temperature, "max_tokens": max_tokens,
            "response_format": {"type": "json_object"}}
    if extra:
        body.update(extra)
    last = ""
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(
                BASE, data=json.dumps(body).encode("utf-8"),
                headers={"Authorization": "Bearer " + _KEY,
                         "Content-Type": "application/json",
                         "HTTP-Referer": "https://github.com/lixvanran/creativity-mechanism-skills",
                         "X-Title": "thinking-surface-eval"})
            with urllib.request.urlopen(req, timeout=240) as resp:
                d = json.loads(resp.read().decode("utf-8"))
            ch = (d.get("choices") or [{}])[0]
            raw = ((ch.get("message") or {}).get("content")) or ""
            txt = strip_think(raw)
            if not txt:
                last = "empty_after_strip_think"
                time.sleep(1.5 * (attempt + 1))
                continue
            m = re.search(r"\{.*\}", txt, re.S)
            try:
                parsed = json.loads(m.group(0) if m else txt)
            except Exception as e:
                return {"ok": False, "text": txt, "parsed": None, "usage": d.get("usage") or {},
                        "parse_error": "json_decode: %s" % str(e)[:80], "model": d.get("model") or model}
            return {"ok": True, "text": txt, "parsed": parsed, "usage": d.get("usage") or {},
                    "model": d.get("model") or model}
        except urllib.error.HTTPError as e:
            try:
                last = "HTTP%d:%s" % (e.code, e.read().decode("utf-8")[:180])
            except Exception:
                last = "HTTP%d" % e.code
            if e.code in (429, 500, 502, 503, 529):
                time.sleep(3.0 * (attempt + 1) + random.random() * 3)
                continue
            return {"ok": False, "text": "", "parsed": None, "usage": {},
                    "parse_error": "http_error", "error": last, "model": model}
        except Exception as e:
            last = "%s: %s" % (type(e).__name__, str(e)[:120])
            time.sleep(2.0 * (attempt + 1))
    return {"ok": False, "text": "", "parsed": None, "usage": {},
            "parse_error": "call_failed", "error": last, "model": model}
