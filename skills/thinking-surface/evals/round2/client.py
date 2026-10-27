"""MiniMax 原生 API 客户端。

纪律（贯穿全项目）：
1. 失败路径不静默归零 —— 空输出 / 截断 / 解析失败 / HTTP 错误，一律返回 ok=False 或带明确 flag，
   绝不返回「看起来像 0 的成功值」。
2. 通道健康度与读数分开报 —— 上层必须能区分「没生成」和「生成了但是空/截断」。
3. 凭据只走 header，绝不进 URL / 日志 / 异常消息。
"""
from __future__ import annotations

import json
import os
import random
import re
import time
import urllib.error
import urllib.request

BASE = "https://api.minimaxi.com/v1/chat/completions"
_KEY = os.environ.get("MINIMAX_SUBSCRIPTION_KEY", "")
if not _KEY:
    raise RuntimeError("MINIMAX_SUBSCRIPTION_KEY 未设置：拒绝在没有凭据的情况下假装跑实验")

_THINK_RE = re.compile(r"<think>.*?</think>", re.S)


def strip_think(text: str) -> str:
    """去掉 <think>...</think> 思考块（若模型内联返回）。"""
    return _THINK_RE.sub("", text or "").strip()


def chat(
    messages,
    model: str = "MiniMax-M2.7",
    temperature: float = 0.7,
    max_tokens: int = 1600,
    timeout: int = 240,
    retries: int = 3,
    extra: dict | None = None,
) -> dict:
    """发一次对话。返回统一 record，字段含义见 module docstring。"""
    body = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if extra:
        body.update(extra)

    last_err = None
    for attempt in range(1, retries + 1):
        t0 = time.time()
        try:
            req = urllib.request.Request(
                BASE,
                data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                headers={
                    "Authorization": "Bearer " + _KEY,
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
            d = json.loads(raw)
            ch = (d.get("choices") or [{}])[0]
            msg = ch.get("message") or {}
            text = strip_think(msg.get("content") or "")
            usage = d.get("usage") or {}
            finish = ch.get("finish_reason")
            rec = {
                "ok": bool(text) and finish != "error",
                "text": text,
                "raw_len": len(text),
                "finish_reason": finish,
                "truncated": finish == "length",
                "usage": usage,
                "latency": round(time.time() - t0, 2),
                "attempts": attempt,
                "model": model,
                "error": None,
                "failure_kind": None,
            }
            if not text:
                # 空输出 = 失败，绝不伪装成「模型认为无内容」
                rec["ok"] = False
                rec["failure_kind"] = "empty_output"
            elif rec["truncated"]:
                rec["failure_kind"] = "truncated"  # 截断：内容半残，调用层成功、产出层受损
            return rec
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8")[:300]
            except Exception:
                pass
            last_err = f"HTTP{e.code}:{detail}"
            if e.code == 429 and attempt < retries:
                # 速率限制：退避要长（配额的秒级窗口不是指数退避能解决的）
                time.sleep(min(45.0, 8.0 * attempt) * (0.7 + 0.6 * random.random()))
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}:{e}"
        if attempt < retries and "429" not in str(last_err):
            time.sleep(min(8.0, 1.5 * (2 ** (attempt - 1))) * (0.6 + 0.8 * random.random()))
    return {
        "ok": False,
        "text": "",
        "raw_len": 0,
        "finish_reason": None,
        "truncated": False,
        "usage": {},
        "latency": round(time.time() - t0, 2),
        "attempts": retries,
        "model": model,
        "error": last_err,
        "failure_kind": "transport_error",
    }


def json_call(
    messages,
    schema_hint: str = "",
    model: str = "MiniMax-M2.7",
    temperature: float = 0.0,
    max_tokens: int = 1200,
    retries: int = 2,
    thinking: str | None = None,
) -> dict:
    """要求模型只吐 JSON。解析失败显式记录（parse_error），不吞。

    thinking="disabled"：关掉思考块。判官类调用一律用它——
    理由有二：① 思考 token 会吃光 max_tokens 导致 JSON 输出不完整（实测踩过）
    ② 思考 token 直接消耗速率配额，高并发下把通道打到 429（实测踩过）。
    """
    sys_msg = (
        "你是一个只输出 JSON 的机器。不要输出解释、不要 markdown 代码块、"
        "不要输出思考过程。第一个字符必须是 { 或 [。"
    )
    if schema_hint:
        sys_msg += "\n输出结构必须符合：" + schema_hint
    extra = {"thinking": {"type": thinking}} if thinking else None
    rec = chat(
        [{"role": "system", "content": sys_msg}] + list(messages),
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        retries=retries,
        extra=extra,
    )
    if not rec["ok"]:
        rec["parsed"] = None
        rec["parse_error"] = "call_failed:" + str(rec.get("failure_kind"))
        return rec
    txt = rec["text"].strip()
    # 容错：截断出第一个完整 JSON 块
    m = re.search(r"[\{\[].*[\}\]]", txt, re.S)
    payload = m.group(0) if m else txt
    try:
        obj = json.loads(payload)
        rec["parsed"] = obj
        rec["parse_error"] = None
    except Exception as e:  # noqa: BLE001
        rec["parsed"] = None
        rec["parse_error"] = f"json_decode:{type(e).__name__}"
    return rec
