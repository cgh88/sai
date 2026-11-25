# -*- coding: utf-8 -*-
"""API 통합 테스트 — 시드 모드(기본)와 실시간 Liner 경로(목 서버)를 모두 검증한다."""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

os.environ.setdefault("SAI_STREAM_SPEED", "0")       # 시드 스트림 지연 제거
os.environ.pop("LINER_API_KEY", None)

import main  # noqa: E402
import settings as settings_mod  # noqa: E402
from liner_client import LinerClient  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c


def test_health_seed_mode(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["liner"]["configured"] is False
    assert body["liner"]["mode"] == "seed"
    assert body["rules"]["engine"] == "sai-rule-engine"
    text = json.dumps(body, ensure_ascii=False)
    assert "api_key" not in text.lower()


def test_config_presets(client):
    body = client.get("/api/config").json()
    labels = [p["label"] for p in body["presets"]["noise"]]
    assert any("58dB" in l for l in labels)
    assert body["presets"]["noise"][0]["case_id"] == "C-003"
    assert body["presets"]["parking"][0]["case_id"] == "C-007"
    assert "가상 데이터" in body["disclaimer"]


def test_noise_analyze(client):
    res = client.post("/api/noise/analyze", json={
        "case_id": "C-003", "at": "23:20", "leq": 37, "lmax": 58, "repeat_count": 3})
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == "C-003"
    r = body["result"]
    assert r["result"] == "기준 초과"
    assert r["severity"]["label"] == "기준 초과 · 주의"
    assert r["exceeded_db"] == 6.0
    assert r["lmax_hits"] == 3
    assert len(r["citations"]) == 3
    assert r["gate"] == "자동 처리"
    assert "302호 거주자님께" in body["letter"]
    assert body["checks"] and all(c["ok"] for c in body["checks"])


def test_noise_analyze_validation(client):
    assert client.post("/api/noise/analyze", json={"at": "23:20", "noise_type": "nope"}).status_code == 400


def test_parking_analyze_and_masking(client):
    res = client.post("/api/parking/analyze", json={
        "case_id": "C-007", "zone": "fire", "shot_at": "19:12", "plate_ocr": "12가3456"})
    body = res.json()
    assert body["result"]["fine"] == 500000
    assert body["payload"]["plate_ocr"] == "12가****"      # 응답에 원본 번호판이 없다
    assert "12가3456" not in json.dumps(body, ensure_ascii=False).replace("12가****", "")
    assert body["result"]["authority"] == "관할 소방서"


def test_legal_stream_seed(client):
    client.post("/api/noise/analyze", json={"case_id": "C-003", "at": "23:20", "leq": 37, "lmax": 58,
                                            "repeat_count": 3})
    with client.stream("GET", "/api/legal/stream?case_id=C-003") as res:
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/event-stream")
        raw = "".join(chunk for chunk in res.iter_text())
    events = [json.loads(line[5:]) for line in raw.splitlines() if line.startswith("data:")]
    types = [e["type"] for e in events]
    assert types[0] == "mode" and events[0]["mode"] == "seed"
    assert "references" in types
    # 근거(references)가 본문(text-delta)보다 먼저 도착한다
    assert types.index("references") < types.index("text-delta")
    assert types[-1] == "finish"
    refs = next(e for e in events if e["type"] == "references")["references"]
    assert len(refs) == 3
    deltas = "".join(e["delta"] for e in events if e["type"] == "text-delta")
    assert "[1]" in deltas and "34" in deltas


def test_letter_and_report(client):
    letter = client.post("/api/case/C-003/letter", json={}).json()
    assert letter["letter"]
    assert [c["label"] for c in letter["checks"]] == ["비난 없음", "요구는 하나", "기한은 부드럽게"]
    assert all(c["ok"] for c in letter["checks"])
    assert letter["meta"]["source"] in ("seed", "liner")

    rep = client.post("/api/case/C-003/report", json={}).json()
    labels = [f["label"] for f in rep["fields"]]
    assert "기준 대비" in labels and "근거 조문" in labels and "책임 경계" in labels
    assert rep["summary"]
    assert "중재 보고서" in rep["markdown"]
    assert "12가3456" not in rep["markdown"]


def test_send_changes_status(client):
    res = client.post("/api/case/C-003/send").json()
    assert res["ok"] and res["toast"] == "전송 완료 · 관리소에 기록됨"
    detail = client.get("/api/case/C-003").json()
    assert detail["status"] == "발송 완료"


def test_dashboard(client):
    body = client.get("/api/dashboard").json()
    assert body["counts"]["today"] == 5
    assert len(body["cases"]) == 5
    assert len(body["kpis"]) == 4
    assert body["kpis"][1]["delta_pct"] == -70          # 90 → 27분
    assert body["cases"][0]["urgency"] == "긴급"          # 소방구역 건이 최상단
    assert body["citation_log"]
    assert "가상 데이터" in body["disclaimer"]
    # 대시보드 어디에도 원본 차량번호가 없다
    assert "12가3456" not in json.dumps(body, ensure_ascii=False)


def test_approve_action(client):
    before = client.get("/api/dashboard").json()["counts"]["pending"]
    res = client.post("/api/case/C-007/action", json={"action": "approve"}).json()
    assert res["ok"]
    after = res["dashboard"]["counts"]["pending"]
    assert after <= before
    assert res["case"]["status"] in ("발송 완료", "이동 요청 발송")


def test_missing_case_404(client):
    assert client.get("/api/case/NOPE").status_code == 404
    assert client.get("/api/legal/stream?case_id=NOPE").status_code == 404


def test_static_views(client):
    for path in ("/", "/3d_viewer.html", "/print.html", "/css/app.css", "/js/app.js",
                 "/vendor/three.module.js", "/vendor/addons/loaders/GLTFLoader.js",
                 "/assets/parking_fire.jpg"):
        assert client.get(path).status_code == 200, path


# ────────────────────────────────────────────────────────────────
# 실시간 Liner 경로 — 목 서버(실제 SSE 규격)로 검증
# ────────────────────────────────────────────────────────────────
def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def mock_liner():
    import uvicorn
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import mock_liner_server

    port = _free_port()
    config = uvicorn.Config(mock_liner_server.app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(80):
        if server.started:
            break
        time.sleep(0.1)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture()
def live_client(mock_liner, monkeypatch):
    settings = settings_mod.Settings(api_key="test-key", base_url=mock_liner, demo_mode="off")
    monkeypatch.setattr(main, "SETTINGS", settings)
    monkeypatch.setattr(main, "CLIENT", LinerClient("test-key", mock_liner))
    main.STORE.reset()
    with TestClient(main.app) as c:
        yield c
    main.STORE.reset()


def test_live_health_balance(live_client):
    body = live_client.get("/api/health").json()
    assert body["liner"]["configured"] is True
    assert body["liner"]["mode"] == "live"
    assert body["liner"]["balance_usd"] == "12.500000"
    assert "test-key" not in json.dumps(body)


def test_live_search_stream_relay(live_client):
    live_client.post("/api/noise/analyze", json={"case_id": "C-003", "at": "23:20", "leq": 37,
                                                 "lmax": 58, "repeat_count": 3})
    with live_client.stream("GET", "/api/legal/stream?case_id=C-003") as res:
        raw = "".join(chunk for chunk in res.iter_text())
    events = [json.loads(line[5:]) for line in raw.splitlines() if line.startswith("data:")]
    assert events[0]["type"] == "mode" and events[0]["mode"] == "live"
    refs = next(e for e in events if e["type"] == "references")["references"]
    assert refs[0]["hostname"] == "law.go.kr"
    deltas = "".join(e["delta"] for e in events if e["type"] == "text-delta")
    assert "34 dB(A)" in deltas
    assert events[-1]["type"] == "finish"
    assert any(e["type"] == "finish" and e.get("citations") == 2 for e in events)


def test_live_letter_uses_router(live_client):
    live_client.post("/api/noise/analyze", json={"case_id": "C-003", "at": "23:20", "leq": 37,
                                                 "lmax": 58, "repeat_count": 3})
    body = live_client.post("/api/case/C-003/letter", json={}).json()
    assert body["meta"]["source"] == "liner"
    assert body["meta"]["model"] == "gpt-6-luna"          # 라우터가 고른 응답 모델
    assert body["meta"]["routing_strategy"] == "balanced"
    assert body["meta"]["usage"]["cost_usd"] == 0.0154
    assert "302호 거주자님께" in body["letter"]


def test_live_report_uses_cost_routing(live_client):
    live_client.post("/api/noise/analyze", json={"case_id": "C-003", "at": "23:20", "leq": 37,
                                                 "lmax": 58, "repeat_count": 3})
    body = live_client.post("/api/case/C-003/report", json={}).json()
    assert body["meta"]["source"] == "liner"
    assert body["summary"]


def test_live_failure_falls_back_to_seed(monkeypatch):
    """키가 틀리거나 Liner 가 죽으면 화면은 시드로 폴백하고 그 사실을 배지로 알린다."""
    monkeypatch.setattr(main, "SETTINGS", settings_mod.Settings(
        api_key="wrong-key", base_url="http://127.0.0.1:9", demo_mode="off"))
    monkeypatch.setattr(main, "CLIENT", LinerClient("wrong-key", "http://127.0.0.1:9"))
    main.STORE.reset()
    with TestClient(main.app) as c:
        c.post("/api/noise/analyze", json={"case_id": "C-003", "at": "23:20", "leq": 37, "lmax": 58,
                                           "repeat_count": 3})
        with c.stream("GET", "/api/legal/stream?case_id=C-003") as res:
            raw = "".join(chunk for chunk in res.iter_text())
    events = [json.loads(line[5:]) for line in raw.splitlines() if line.startswith("data:")]
    modes = [e for e in events if e["type"] == "mode"]
    assert modes[0]["mode"] == "live"
    assert any(m.get("fallback") for m in modes[1:])
    assert any(e["type"] == "references" for e in events)
    main.STORE.reset()
