# -*- coding: utf-8 -*-
"""Liner API 목 서버 — 실제 응답 규격(SSE 이벤트 이름·필드)을 그대로 흉내 낸다.

용도: LINER_API_KEY 없이도 [실시간 Liner API] 경로(SSE 중계·Router 문장 생성·크레딧 조회)를
      통합 테스트로 검증한다. 계약(contract)이 바뀌면 이 목도 같이 고친다.

단독 실행:
    python3 backend/tests/mock_liner_server.py 8099
"""

from __future__ import annotations

import json
import sys
import time

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

API_KEY = "test-key"
app = FastAPI(title="mock-liner")

REFERENCES = [
    {
        "title": "공동주택 층간소음의 범위와 기준에 관한 규칙 (제3조 및 별표)",
        "url": "https://www.law.go.kr/법령/공동주택층간소음의범위와기준에관한규칙",
        "hostname": "law.go.kr",
        "faviconUrl": None,
        "description": "야간 직접충격 소음 1분 등가소음도 34 dB(A), 최고소음도 52 dB(A), 1시간 내 3회 이상 초과 시 기준 초과.",
        "date": "2023-01-02",
        "searchQuery": "층간소음 야간 기준",
    },
    {
        "title": "공동주택관리법 제20조 (층간소음 기준 초과 시 관리주체의 조치)",
        "url": "https://www.law.go.kr/법령/공동주택관리법",
        "hostname": "law.go.kr",
        "description": "기준 초과 시 관리주체는 해당 세대에 알리고 조치·기록을 하여야 한다.",
        "date": "2024-07-01",
        "searchQuery": "층간소음 야간 기준",
    },
]

ANSWER = (
    "야간 직접충격 소음의 1분 등가소음도 기준은 34 dB(A)입니다 [1]. "
    "최고소음도는 52 dB(A)이며 1시간 내 3회 이상 넘으면 기준 초과로 봅니다 [1]. "
    "기준을 넘으면 관리주체는 공동주택관리법 제20조에 따라 조치·기록 의무를 집니다 [2]."
)


def _auth(key: str | None):
    if key != API_KEY:
        raise HTTPException(status_code=401, detail={"error": {"code": "invalid_api_key", "message": "invalid key"}})


@app.get("/api/v1/credits/balance")
async def balance(x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    return {"billing_type": "prepaid", "balance": 12500000, "balance_usd": "12.500000", "currency": "USD"}


@app.post("/api/v1/agents/search")
async def search(request: Request, x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    body = await request.json()
    assert body["messages"][-1]["role"] == "user"
    if not body.get("stream", True):
        return {"answer": ANSWER, "references": REFERENCES, "chunks": []}

    async def gen():
        def sse(obj):
            return f"event: data\ndata: {json.dumps(obj, ensure_ascii=False)}\n\n"

        yield sse({"type": "start", "message_id": "msg_test",
                   "message_metadata": {"request_id": body.get("request_id", ""), "trace_id": "api_ai_search_mock"}})
        yield sse({"type": "start-step"})
        yield sse({"type": "data-search-references", "id": "data-search-references-abcd1234",
                   "data": {"references": REFERENCES}})
        yield sse({"type": "data-search-chunks", "id": "data-search-chunks-abcd1234",
                   "data": {"referenceChunks": [{"num": 1, "content": "야간 34 dB(A)…", "sourceTitle": REFERENCES[0]["title"],
                                                 "sourceUrl": REFERENCES[0]["url"]}]}})
        yield sse({"type": "text-start", "id": "text-1"})
        for piece in [ANSWER[i:i + 24] for i in range(0, len(ANSWER), 24)]:
            yield sse({"type": "text-delta", "id": "text-1", "delta": piece})
            await _sleep()
        yield sse({"type": "text-end", "id": "text-1"})
        yield sse({"type": "finish-step"})
        yield sse({"type": "finish"})
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


async def _sleep():
    import asyncio
    await asyncio.sleep(0.01)


@app.post("/api/v1/chat/completions")
async def chat(request: Request, x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    body = await request.json()
    if body.get("model", "").endswith("-router") and body.get("routing_strategy") not in (None, "cost", "balanced", "quality"):
        raise HTTPException(400, detail={"error": {"code": "invalid_request", "message": "routing_strategy must be one of: cost, balanced, quality"}})
    system = (body["messages"][0].get("content") or "")[:20]
    content = (
        "302호 거주자님께 — 지난 11월 22일(일) 밤 11시 20분부터 11시 36분까지 401호에서 발소리로 추정되는 소리가 "
        "반복되었습니다. 최고소음도는 58 dB(A)로 야간 기준(52 dB(A))을 넘는 순간이 1시간 내 3회 이상 있었습니다. "
        "다음 날 학교에 가야 하는 아이가 있어 밤 11시 이후에는 조용한 환경이 꼭 필요합니다. 소리가 나쁜 마음에서였다고는 "
        "생각하지 않습니다. 다만 이 시간대만큼은 슬리퍼 착용과 아이의 뛰는 놀이를 잠시 멈춰 주시면 저희가 훨씬 편안해질 "
        "것 같습니다. 바로 답을 주지 않으셔도 괜찮습니다."
    )
    return {
        "id": "chatcmpl-mock",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "gpt-6-luna",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1200, "completion_tokens": 210, "cost": 0.0154},
        "mock_hint": system,
    }


if __name__ == "__main__":
    import uvicorn
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8099
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
