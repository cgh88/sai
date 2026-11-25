# -*- coding: utf-8 -*-
"""「사이(Sai)」 본체 API — FastAPI.

화면(4뷰)은 같은 서버가 정적으로 서빙한다. 실행:
    cd sai-app && uvicorn backend.main:app --port 8000
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # uvicorn backend.main:app 로도 동작하게

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

import documents
import prompts
import rule_engine
import seed_data
from liner_client import LinerClient, LinerError
from settings import get_settings
from store import STORE

APP_VERSION = "1.0.0"
STARTED_AT = time.time()

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
SETTINGS = get_settings()
CLIENT = LinerClient(SETTINGS.api_key, SETTINGS.base_url)

app = FastAPI(title="사이(Sai) — 공동주택 갈등 자율조정 AI 에이전트", version=APP_VERSION)


# ────────────────────────────────────────────────────────────────
# 정적 화면
# ────────────────────────────────────────────────────────────────
def _file(name: str) -> FileResponse:
    path = FRONTEND / name
    if not path.is_file():
        raise HTTPException(404, f"{name} 없음")
    return FileResponse(path, headers={"Cache-Control": "no-store"})


@app.get("/", include_in_schema=False)
async def index():
    return _file("index.html")


@app.get("/print.html", include_in_schema=False)
async def print_view():
    return _file("print.html")


@app.get("/3d_viewer.html", include_in_schema=False)
async def three_d():
    return _file("3d_viewer.html")


@app.get("/css/{name}", include_in_schema=False)
async def css(name: str):
    return _file(f"css/{name}")


@app.get("/js/{name}", include_in_schema=False)
async def js(name: str):
    return _file(f"js/{name}")


@app.get("/vendor/{path:path}", include_in_schema=False)
async def vendor(path: str):
    root = (FRONTEND / "vendor").resolve()
    target = (root / path).resolve()
    if not str(target).startswith(str(root)) or not target.is_file():
        raise HTTPException(404, "vendor 없음")
    return FileResponse(target, headers={"Cache-Control": "public, max-age=86400"})


@app.get("/assets/{name}", include_in_schema=False)
async def assets(name: str):
    path = (FRONTEND / "assets" / name).resolve()
    if not str(path).startswith(str((FRONTEND / "assets").resolve())) or not path.is_file():
        raise HTTPException(404, "asset 없음")
    return FileResponse(path)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)


# ────────────────────────────────────────────────────────────────
# 모델
# ────────────────────────────────────────────────────────────────
class NoiseIn(BaseModel):
    case_id: str | None = None
    noise_type: str = "impact"                 # impact | air | out_of_scope
    sound_label: str = "발소리"
    at: str = "23:20"                          # HH:MM 또는 ISO
    leq: float = 37.0
    lmax: float | None = 58.0
    repeat_count: int = Field(3, ge=1, le=10)
    duration_min: int = 20
    confidence: float = 0.94
    message: str = ""
    household_context: str = ""
    request: str = ""
    complex_name: str = seed_data.COMPLEX["name"]
    approval_date: str = seed_data.COMPLEX["approval_date"]
    unit_from: str = "401"
    unit_to: str = "302"


class ParkingIn(BaseModel):
    case_id: str | None = None
    zone: str = "fire"
    location: str = "지하 2층 B-27 소방자동차 전용구역"
    shot_at: str = "19:12"
    plate_ocr: str = "12가3456"
    prior_violations_12m: int = 0
    confidence: float = 0.91
    shots: int = 2
    photo_preset: str = "fire"
    complex_name: str = seed_data.COMPLEX["name"]


class ActionIn(BaseModel):
    action: str = "approve"                    # approve | hold


# ────────────────────────────────────────────────────────────────
# 유틸
# ────────────────────────────────────────────────────────────────
def _full_at(value: str) -> str:
    """'23:20' → 오늘 날짜 + 시각(ISO)."""
    text = (value or "").strip()
    if "T" in text or " " in text:
        return rule_engine.parse_dt(text).isoformat(timespec="minutes")
    hh, mm = (text.split(":") + ["00"])[:2]
    day = datetime.now().date()
    return datetime.combine(day, datetime.min.time()).replace(hour=int(hh), minute=int(mm)).isoformat(timespec="minutes")


def _events_from(inp: NoiseIn) -> list[dict]:
    base = rule_engine.parse_dt(_full_at(inp.at))
    events = []
    for i in range(inp.repeat_count):
        events.append({
            "at": (base + timedelta(minutes=8 * i)).isoformat(timespec="minutes"),
            "lmax": inp.lmax if inp.lmax is not None else 0,
            "leq": inp.leq,
        })
    return events


def _noise_payload(inp: NoiseIn) -> dict:
    return {
        "kind": "noise",
        "case_id": inp.case_id or "",
        "complex": {"name": inp.complex_name, "approval_date": inp.approval_date},
        "unit": {"from": inp.unit_from, "to": inp.unit_to},
        "noise_type": inp.noise_type,
        "sound_label": inp.sound_label,
        "duration_min": inp.duration_min,
        "confidence": inp.confidence,
        "message": inp.message,
        "household_context": inp.household_context or "다음 날 학교에 가야 하는 아이가 있어 밤 11시 이후에는 조용한 환경이 꼭 필요합니다.",
        "request": inp.request or "슬리퍼 착용과 아이의 뛰는 놀이를 잠시 멈춰 주시면",
        "events": _events_from(inp),
    }


def _parking_payload(inp: ParkingIn) -> dict:
    return {
        "kind": "parking",
        "case_id": inp.case_id or "",
        "complex": {"name": inp.complex_name, "approval_date": seed_data.COMPLEX["approval_date"]},
        "zone": inp.zone,
        "location": inp.location,
        "shot_at": _full_at(inp.shot_at),
        "plate_ocr": inp.plate_ocr,
        "prior_violations_12m": inp.prior_violations_12m,
        "confidence": inp.confidence,
        "shots": inp.shots,
        "preset_photo": inp.photo_preset,
    }


def _case_out(case: dict) -> dict:
    """프론트로 보내는 케이스 — payload 원문(차량번호 등)은 마스킹해서 내보낸다."""
    payload = {**case["payload"]}
    if payload.get("plate_ocr"):
        payload["plate_ocr"] = rule_engine.mask_plate(payload["plate_ocr"])
    return {
        "id": case["id"],
        "kind": case["kind"],
        "status": case["status"],
        "urgency": case["urgency"],
        "received_at": case["received_at"],
        "assignee": case.get("assignee", ""),
        "note": case.get("note", ""),
        "processing_min": case.get("processing_min"),
        "letter_min": case.get("letter_min"),
        "letter": case.get("letter", ""),
        "letter_source": case.get("letter_source", "seed"),
        "checks": case.get("checks", []),
        "summary": case.get("summary", ""),
        "report": case.get("report", []),
        "payload": payload,
        "result": case["result"],
        "disclaimer": seed_data.DISCLAIMER,
        "boundary": case["result"].get("boundary", ""),
        "updated_at": case.get("updated_at", ""),
    }


# ────────────────────────────────────────────────────────────────
# 상태 · 설정 · 프리셋
# ────────────────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    """서버 상태 + Liner 크레딧 잔액 확인(키가 있으면 실제 호출, 없으면 시드 모드)."""
    liner = {
        "configured": SETTINGS.has_key,
        "mode": "seed" if SETTINGS.use_seed else "live",
        "base_url": SETTINGS.base_url,
        "chat_model": SETTINGS.chat_model,
        "balance_usd": None,
        "note": "",
        "checked": False,
    }
    if SETTINGS.has_key and not SETTINGS.use_seed:
        try:
            bal = await CLIENT.credits_balance()
            liner.update(checked=True, balance_usd=bal.get("balance_usd"),
                         balance_raw=bal.get("balance"), latency_ms=bal.get("latency_ms"))
        except LinerError as exc:
            liner.update(checked=True, note=exc.as_dict())
        except Exception as exc:                                    # noqa: BLE001 — 네트워크
            liner.update(checked=True, note={"kind": "network", "message": type(exc).__name__})
    else:
        liner["note"] = "Liner API 키 미설정 — 데모 시드 모드로 동작합니다(모든 판정·문서 흐름은 동일)."
    return {
        "status": "ok",
        "app": {"name": "사이(Sai)", "version": APP_VERSION,
                "uptime_s": int(time.time() - STARTED_AT), "now": datetime.now().isoformat(timespec="seconds")},
        "liner": liner,
        "rules": {"engine": rule_engine.ENGINE_NAME, "version": rule_engine.ENGINE_VERSION},
        "demo": {"disclaimer": seed_data.DISCLAIMER, "seed_mode": SETTINGS.use_seed},
    }


@app.get("/api/config")
async def config():
    return {
        "settings": SETTINGS.public(),
        "standards": rule_engine.standards(),
        "disclaimer": seed_data.DISCLAIMER,
        "presets": {
            "noise": [
                {"id": "case3", "label": "23:20 · 58dB(A) · 발소리", "case_id": "C-003",
                 "payload": seed_data.noise_preset("C-003", "case3")},
                {"id": "scene6", "label": "23:20 · 등가 42dB (씬 6 대본값)", "case_id": "C-008",
                 "payload": seed_data.noise_preset("C-008", "scene6")},
            ],
            "parking": [
                {"id": "case7", "label": "소방차 전용구역 · 19:12", "case_id": "C-007",
                 "payload": seed_data.parking_preset("C-007", "case7")},
                {"id": "aisle", "label": "통로 이중주차 · 21:40", "case_id": "C-005",
                 "payload": seed_data.parking_preset("C-005", "aisle")},
            ],
        },
        "views": ["slides", "mobile", "twin", "dashboard"],
    }


@app.post("/api/demo/reset")
async def demo_reset():
    STORE.reset()
    return {"ok": True, "cases": len(STORE.cases), "disclaimer": seed_data.DISCLAIMER}


# ────────────────────────────────────────────────────────────────
# 1단 판정 (즉시·결정론적)
# ────────────────────────────────────────────────────────────────
@app.post("/api/noise/analyze")
async def noise_analyze(inp: NoiseIn):
    payload = _noise_payload(inp)
    try:
        case = STORE.upsert(payload, received_at=payload["events"][0]["at"])
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    STORE.log_citation(case_id=case["id"], query_kind="noise", citations=len(case["result"]["citations"]),
                       docs=[f"{c['doc']} {c['article']}" for c in case["result"]["citations"]],
                       gate=case["result"]["gate"])
    out = _case_out(case)
    out["mode"] = "seed" if SETTINGS.use_seed else "live"
    out["query"] = prompts.noise_query(case["result"], case["payload"])
    return out


@app.post("/api/parking/analyze")
async def parking_analyze(inp: ParkingIn):
    payload = _parking_payload(inp)
    try:
        case = STORE.upsert(payload, received_at=payload["shot_at"])
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    STORE.log_citation(case_id=case["id"], query_kind="parking", citations=len(case["result"]["citations"]),
                       docs=[f"{c['doc']} {c['article']}" for c in case["result"]["citations"]],
                       gate=case["result"]["gate"])
    out = _case_out(case)
    out["mode"] = "seed" if SETTINGS.use_seed else "live"
    out["query"] = prompts.parking_query(case["result"], case["payload"])
    return out


@app.get("/api/case/{case_id}")
async def case_detail(case_id: str):
    case = STORE.get(case_id)
    if not case:
        raise HTTPException(404, "케이스 없음")
    return _case_out(case)


# ────────────────────────────────────────────────────────────────
# Liner Search Agent — SSE 중계 (근거가 문장보다 먼저 도착)
# ────────────────────────────────────────────────────────────────
def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _chunk_text(text: str, size: int = 22) -> list[str]:
    return [text[i:i + size] for i in range(0, len(text), size)]


async def _seed_stream(payload: dict, kind: str, case_id: str):
    seed = seed_data.evidence_seed(kind)
    speed = SETTINGS.stream_speed

    async def wait(seconds: float):
        if speed > 0:
            await asyncio.sleep(seconds * speed)

    yield _sse({"type": "mode", "mode": "seed", "endpoint": "/api/v1/agents/search",
                "model": "seed-reference", "request_id": f"seed-{case_id}-{int(time.time())}"})
    await wait(0.25)
    yield _sse({"type": "references", "references": seed["references"],
                "note": "Liner Search Agent 응답 포맷(references)을 그대로 재생"})
    await wait(0.2)
    yield _sse({"type": "chunks", "chunks": seed["chunks"]})
    await wait(0.15)
    yield _sse({"type": "text-start"})
    for piece in _chunk_text(seed["answer"]):
        await wait(0.075)
        yield _sse({"type": "text-delta", "delta": piece})
    yield _sse({"type": "text-end"})
    await wait(0.1)
    yield _sse({"type": "finish", "elapsed_ms": int(3.2 * 1000), "citations": len(seed["references"])})
    STORE.last_evidence[case_id] = seed["answer"]


@app.get("/api/legal/stream")
async def legal_stream(case_id: str, q: str | None = None):
    case = STORE.get(case_id)
    if not case:
        raise HTTPException(404, "케이스 없음")
    result, payload = case["result"], case["payload"]
    query = q or (prompts.parking_query(result, payload) if result["kind"] == "parking"
                  else prompts.noise_query(result, payload))

    async def generator():
        if SETTINGS.use_seed or not SETTINGS.has_key:
            async for chunk in _seed_stream(payload, result["kind"], case_id):
                yield chunk
            return

        yield _sse({"type": "mode", "mode": "live", "endpoint": "/api/v1/agents/search",
                    "model": "search-agent", "request_id": f"sai-{case_id}"})
        refs: list[dict] = []
        try:
            async for event in CLIENT.search_stream(query, lang="ko", mode="general",
                                                    request_id=f"sai-{case_id}-{int(time.time())}"):
                etype = event.get("type")
                if etype == "data-search-references":
                    refs = (event.get("data") or {}).get("references") or []
                    yield _sse({"type": "references", "references": refs})
                elif etype == "data-search-chunks":
                    yield _sse({"type": "chunks", "chunks": (event.get("data") or {}).get("referenceChunks") or []})
                elif etype == "text-delta":
                    yield _sse({"type": "text-delta", "delta": event.get("delta", "")})
                elif etype in ("text-start", "text-end"):
                    yield _sse({"type": etype})
                elif etype == "data-error":
                    yield _sse({"type": "error", "message": str((event.get("data") or {}).get("message", "검색 오류"))[:200]})
                elif etype == "_relay_finish":
                    yield _sse({"type": "finish", "elapsed_ms": event.get("elapsed_ms"),
                                "citations": len(refs)})
                    STORE.log_citation(case_id=case_id, query_kind=result["kind"], citations=len(refs),
                                       docs=[r.get("title", "")[:40] for r in refs], gate=result["gate"])
            STORE.last_evidence[case_id] = STORE.last_evidence.get(case_id, "")
        except Exception as exc:                                    # noqa: BLE001 — 실패하면 시드로 폴백
            reason = exc.as_dict() if isinstance(exc, LinerError) else {"kind": "network", "message": type(exc).__name__}
            yield _sse({"type": "mode", "mode": "seed", "fallback": True, "reason": reason})
            async for chunk in _seed_stream(payload, result["kind"], case_id):
                yield chunk

    return StreamingResponse(generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ────────────────────────────────────────────────────────────────
# 2단 — Liner Router 로 문장 생성
# ────────────────────────────────────────────────────────────────
async def _letter_live(case: dict) -> dict | None:
    result = case["result"]
    evidence = STORE.last_evidence.get(case["id"], "")
    messages = [
        {"role": "system", "content": prompts.LETTER_SYSTEM},
        {"role": "user", "content": prompts.letter_user_prompt(result, case["payload"], evidence)},
    ]
    return await CLIENT.chat(messages, model=SETTINGS.chat_model,
                             routing_strategy=SETTINGS.routing_letter, temperature=0.25, max_tokens=700)


@app.post("/api/case/{case_id}/letter")
async def letter(case_id: str):
    case = STORE.get(case_id)
    if not case:
        raise HTTPException(404, "케이스 없음")
    meta = {"source": "seed", "model": "deterministic-template", "latency_ms": 0,
            "routing_strategy": None, "usage": None, "note": ""}
    letter_text = case["result"].get("nvc_letter") or case.get("letter", "")

    if SETTINGS.has_key and not SETTINGS.use_seed:
        try:
            resp = await _letter_live(case)
            if resp and resp.get("content"):
                letter_text = resp["content"]
                meta = {"source": "liner", "model": resp["model"], "latency_ms": resp["latency_ms"],
                        "routing_strategy": resp["routing_strategy"], "usage": resp["usage"], "note": ""}
        except LinerError as exc:
            meta["note"] = exc.as_dict()
        except Exception as exc:                                    # noqa: BLE001
            meta["note"] = {"kind": "network", "message": type(exc).__name__}
    else:
        meta["note"] = "시드 모드 — 룰 엔진의 결정론적 NVC 템플릿 사용(문장 구조·수치는 실호출과 동일)"

    case["letter"] = letter_text
    case["letter_source"] = meta["source"]
    case["checks"] = documents.nvc_checks(letter_text)
    case["updated_at"] = datetime.now().isoformat(timespec="seconds")
    return {"case_id": case_id, "letter": letter_text, "checks": case["checks"], "meta": meta,
            "nvc_labels": ["사실", "영향·필요", "요청", "부담 낮추기"]}


@app.post("/api/case/{case_id}/report")
async def report(case_id: str):
    case = STORE.get(case_id)
    if not case:
        raise HTTPException(404, "케이스 없음")
    result, payload = case["result"], case["payload"]
    meta = {"source": "seed", "model": "rule-engine", "latency_ms": 0, "note": ""}
    summary = _summary_fallback(result)

    if SETTINGS.has_key and not SETTINGS.use_seed:
        try:
            resp = await CLIENT.chat(
                [{"role": "system", "content": prompts.REPORT_SYSTEM},
                 {"role": "user", "content": prompts.report_user_prompt(result, payload)}],
                model=SETTINGS.chat_model, routing_strategy=SETTINGS.routing_report,
                temperature=0.2, max_tokens=400,
            )
            if resp.get("content"):
                summary = resp["content"]
                meta = {"source": "liner", "model": resp["model"], "latency_ms": resp["latency_ms"],
                        "note": ""}
        except LinerError as exc:
            meta["note"] = exc.as_dict()
        except Exception as exc:                                    # noqa: BLE001
            meta["note"] = {"kind": "network", "message": type(exc).__name__}
    else:
        meta["note"] = "시드 모드 — 룰 엔진 필드로 요약 생성"

    case["summary"] = summary
    case["report"] = documents.report_fields(result, payload)
    return {
        "case_id": case_id,
        "title": f"중재 보고서 · {case_id}",
        "fields": case["report"],
        "summary": summary,
        "letter": case.get("letter", ""),
        "markdown": documents.report_markdown(case, result, summary),
        "boundary": result["boundary"],
        "meta": meta,
        "issued_at": datetime.now().isoformat(timespec="minutes"),
    }


def _summary_fallback(result: dict) -> str:
    if result["kind"] == "noise":
        return (
            f"{result['band']} 직접충격 소음 신고로 등가 {result['measured']['leq_max']:.0f} dB(A)·"
            f"최고 {result['measured']['lmax_max']:.0f} dB(A)가 확인되어 기준 대비 +{result['exceeded_db']:.0f} dB로 "
            f"판정했습니다. 근거 3건(규칙 별표·공동주택관리법 제20조·관리규약 제18조)을 붙여 조정문을 발송하고 기록했습니다. "
            f"최종 판단과 후속 조치는 관리주체의 권한입니다."
        )
    return (
        f"{result['zone_label']} 위반으로 {result['fine_note']}을 안내하고, 30분의 여유를 둔 이동 요청을 발송했습니다. "
        f"미이동 시 관리소 보고 후 {result['authority']} 안내로 넘어갑니다. 최종 처분은 {result['authority']}의 권한입니다."
    )


@app.post("/api/case/{case_id}/send")
async def send(case_id: str, channel: str = "anonymous"):
    case = STORE.get(case_id)
    if not case:
        raise HTTPException(404, "케이스 없음")
    case["status"] = "발송 완료" if case["kind"] == "noise" else "이동 요청 발송"
    case["note"] = ("익명 전달 완료 · 관리소에 기록됨" if channel == "anonymous"
                    else "알림톡 발송 완료 · 30분 후 미이동 시 관리소 보고")
    case["updated_at"] = datetime.now().isoformat(timespec="seconds")
    STORE.log_citation(case_id=case_id, query_kind=case["kind"], citations=len(case["result"]["citations"]),
                       docs=[f"{c['doc']} {c['article']}" for c in case["result"]["citations"]],
                       gate=case["result"]["gate"], event="발송")
    return {"ok": True, "case_id": case_id, "status": case["status"], "note": case["note"],
            "toast": "전송 완료 · 관리소에 기록됨", "at": documents.delivered_at()}


@app.post("/api/case/{case_id}/action")
async def case_action(case_id: str, body: ActionIn):
    if body.action not in ("approve", "hold"):
        raise HTTPException(400, "action 은 approve 또는 hold")
    case = STORE.approve(case_id, body.action)
    if not case:
        raise HTTPException(404, "케이스 없음")
    return {"ok": True, "case": _case_out(case), "dashboard": STORE.dashboard()}


# ────────────────────────────────────────────────────────────────
# 관리사무소 대시보드
# ────────────────────────────────────────────────────────────────
@app.get("/api/dashboard")
async def dashboard():
    return STORE.dashboard()


@app.get("/api/briefing")
async def briefing():
    data = STORE.dashboard()
    return {"generated_at": data["generated_at"], "rows": data["briefing"],
            "cases": [{"id": c["id"], "kind": data["cases"][i]["kind_label"], "status": c["status"],
                       "processing_min": c["processing_min"]}
                      for i, c in enumerate(STORE.ordered())],
            "disclaimer": data["disclaimer"]}


@app.get("/api/standards")
async def standards():
    return rule_engine.standards()


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    """키·스택을 화면에 내보내지 않는다."""
    return JSONResponse(status_code=500, content={"error": type(exc).__name__,
                                                  "message": "서버 내부 오류 — 자세한 내용은 서버 콘솔에서 확인하세요."})
