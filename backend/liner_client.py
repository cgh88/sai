# -*- coding: utf-8 -*-
"""Liner API 연동 — Search Agent(SSE) · Chat Completions(Router) · Credits balance.

문서 기준(2026-11 확인)
  · POST /api/v1/agents/search      : messages[], lang, mode, stream → SSE (start → data-search-references
                                      → data-search-chunks → text-start → text-delta* → text-end → finish → [DONE])
  · POST /api/v1/chat/completions   : model(liner-gpt-router), routing_strategy(cost|balanced|quality)
  · GET  /api/v1/credits/balance    : {billing_type, balance, balance_usd, currency}

이 모듈은 키를 절대 로그·예외 메시지·응답에 담지 않는다.
"""

from __future__ import annotations

import json
import time
from typing import AsyncIterator

import httpx

SEARCH_PATH = "/api/v1/agents/search"
CHAT_PATH = "/api/v1/chat/completions"
BALANCE_PATH = "/api/v1/credits/balance"


class LinerError(RuntimeError):
    """Liner API 오류 — 상태 코드와 오류 코드만 담는다(키·헤더는 담지 않는다)."""

    def __init__(self, message: str, status: int | None = None, code: str = "", kind: str = "api"):
        super().__init__(message)
        self.status = status
        self.code = code
        self.kind = kind

    def as_dict(self) -> dict:
        return {"kind": self.kind, "status": self.status, "code": self.code, "message": str(self)}


def _scrub(text: str, api_key: str) -> str:
    if api_key and api_key in text:
        text = text.replace(api_key, "***")
    return text[:400]


def _error_from_response(resp: httpx.Response, api_key: str) -> LinerError:
    code, message = "", ""
    try:
        body = resp.json()
        err = (body or {}).get("error") or {}
        if isinstance(err, dict):
            code = str(err.get("code") or err.get("type") or "")
            message = str(err.get("message") or "")
        elif isinstance(err, str):
            message = err
    except Exception:      # noqa: BLE001 — 본문이 JSON 이 아닐 수 있다
        body = None
    if not message:
        message = _scrub(resp.text or "", api_key)
    kind = "quota" if resp.status_code == 402 else "auth" if resp.status_code in (401, 403) else "api"
    return LinerError(message or f"Liner API 오류({resp.status_code})", resp.status_code, code, kind)


class LinerClient:
    def __init__(self, api_key: str, base_url: str = "https://platform.liner.com", timeout: float = 60.0):
        self._key = (api_key or "").strip()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self._key)

    def _headers(self) -> dict:
        if not self._key:
            raise LinerError("LINER_API_KEY 가 설정되지 않았습니다", kind="config")
        return {"x-api-key": self._key, "Content-Type": "application/json", "Accept": "text/event-stream"}

    # ── credits ────────────────────────────────────────────────
    async def credits_balance(self) -> dict:
        started = time.perf_counter()
        async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=5.0)) as client:
            resp = await client.get(self.base_url + BALANCE_PATH, headers={"x-api-key": self._key})
        if resp.status_code >= 400:
            raise _error_from_response(resp, self._key)
        data = resp.json()
        return {
            "billing_type": data.get("billing_type"),
            "balance": data.get("balance"),
            "balance_usd": data.get("balance_usd"),
            "currency": data.get("currency", "USD"),
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }

    # ── Search Agent (SSE) ─────────────────────────────────────
    async def search_stream(
        self,
        query: str,
        *,
        lang: str = "ko",
        mode: str = "general",
        model: str | None = None,
        request_id: str | None = None,
        history: list[dict] | None = None,
    ) -> AsyncIterator[dict]:
        """Liner SSE 이벤트를 dict 로 그대로 흘려보낸다. 마지막에 finish 메타를 덧붙인다."""
        messages = list(history or [])
        messages.append({"role": "user", "content": query})
        body = {
            "messages": messages,
            "model": model,
            "lang": lang,
            "mode": mode,
            "stream": True,
        }
        if request_id:
            body["request_id"] = request_id

        started = time.perf_counter()
        async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout, connect=10.0)) as client:
            async with client.stream("POST", self.base_url + SEARCH_PATH, headers=self._headers(), json=body) as resp:
                if resp.status_code >= 400:
                    raw = await resp.aread()
                    raise LinerError(
                        _scrub(raw.decode("utf-8", "replace"), self._key), resp.status_code, "", 
                        "quota" if resp.status_code == 402 else "auth" if resp.status_code in (401, 403) else "api",
                    )
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if not payload or payload == "[DONE]":
                        continue
                    try:
                        event = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    yield event
        yield {"type": "_relay_finish", "elapsed_ms": int((time.perf_counter() - started) * 1000)}

    async def search_once(self, query: str, *, lang: str = "ko", mode: str = "general") -> dict:
        """stream:false — 근거 카드만 필요할 때(대시보드 로그 등)."""
        body = {"messages": [{"role": "user", "content": query}], "model": None, "lang": lang,
                "mode": mode, "stream": False}
        async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout, connect=10.0)) as client:
            resp = await client.post(self.base_url + SEARCH_PATH, headers=self._headers(), json=body)
        if resp.status_code >= 400:
            raise _error_from_response(resp, self._key)
        data = resp.json()
        return {
            "answer": data.get("answer", ""),
            "references": data.get("references", []) or [],
            "chunks": data.get("chunks", []) or [],
        }

    # ── Chat Completions (Router) ──────────────────────────────
    async def chat(
        self,
        messages: list[dict],
        *,
        model: str = "liner-gpt-router",
        routing_strategy: str = "balanced",
        temperature: float = 0.3,
        max_tokens: int = 1200,
    ) -> dict:
        body = {
            "model": model,
            "messages": messages,
            "routing_strategy": routing_strategy,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        started = time.perf_counter()
        async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout, connect=10.0)) as client:
            resp = await client.post(
                self.base_url + CHAT_PATH,
                headers={**self._headers(), "Accept": "application/json"},
                json=body,
            )
        if resp.status_code >= 400:
            raise _error_from_response(resp, self._key)
        data = resp.json()
        choices = data.get("choices") or []
        content = ""
        if choices:
            content = ((choices[0].get("message") or {}).get("content") or "").strip()
        usage = data.get("usage") or {}
        return {
            "content": content,
            "model": data.get("model", model),
            "routing_strategy": routing_strategy,
            "usage": {
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "cost_usd": usage.get("cost"),
            },
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }
