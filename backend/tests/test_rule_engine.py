# -*- coding: utf-8 -*-
"""1단 룰 엔진 회귀 테스트 — 20건(층간소음 15 · 불법주차 5) + 마스킹·기준표.

PoC 검증 케이스(scripts/sai_rule_engine_poc.py)와 같은 기대값을 쓴다.
실행: pytest -q  (sai-app 디렉터리에서)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import rule_engine as R  # noqa: E402


def _ev(at, lmax, leq):
    return {"at": at, "lmax": lmax, "leq": leq}


def _noise(**kw):
    base = {
        "kind": "noise",
        "complex": {"name": "새들마을 3단지", "approval_date": "2014-05-20"},
        "unit": {"from": "401", "to": "302"},
        "noise_type": "impact",
        "sound_label": "발소리",
        "confidence": 0.93,
        "message": "",
    }
    base.update(kw)
    return base


CASES = [
    # ── 층간소음
    dict(id="N-01", group="층간소음", payload=_noise(events=[
        _ev("2025-11-09T23:20", 58, 37), _ev("2025-11-09T23:28", 57, 36), _ev("2025-11-09T23:39", 59, 38)]),
        expect={"result": "기준 초과", "band": "야간", "thresholds.lmax": 52.0,
                "measured.lmax_max": 59.0, "lmax_hits": 3, "gate": "자동 처리"}),
    dict(id="N-02", group="층간소음", payload=_noise(events=[_ev("2025-11-10T06:00", 56, 37)]),
         expect={"band": "주간", "thresholds.lmax": 57.0, "result": "기준 이내"}),
    dict(id="N-03", group="층간소음", payload=_noise(events=[_ev("2025-11-10T05:59", 56, 37)]),
         expect={"band": "야간", "thresholds.lmax": 52.0, "result": "기준 초과"}),
    dict(id="N-04", group="층간소음", payload=_noise(events=[_ev("2025-11-09T22:00", 53, 35)]),
         expect={"band": "야간", "thresholds.lmax": 52.0, "result": "기준 초과"}),
    dict(id="N-05", group="층간소음", payload=_noise(events=[_ev("2025-11-09T21:59", 53, 35)]),
         expect={"band": "주간", "thresholds.lmax": 57.0, "result": "기준 이내"}),
    dict(id="N-06", group="층간소음",
         payload=_noise(complex={"name": "새들마을 1단지", "approval_date": "2004-03-15"},
                        events=[_ev("2025-11-09T23:10", 53, 35)]),
         expect={"grace.applied": True, "thresholds.lmax": 54.0, "result": "기준 이내"}),
    dict(id="N-07", group="층간소음",
         payload=_noise(complex={"name": "새들마을 2단지", "approval_date": "2008-09-01"},
                        events=[_ev("2025-11-09T23:10", 53, 35), _ev("2025-11-09T23:20", 53, 35),
                                _ev("2025-11-09T23:30", 53, 35)]),
         expect={"grace.applied": False, "thresholds.lmax": 52.0, "result": "기준 초과"}),
    dict(id="N-08", group="층간소음",
         payload=_noise(complex={"name": "새들마을 1단지", "approval_date": "2004-03-15"},
                        events=[_ev("2024-12-31T23:10", 53, 35)]),
         expect={"grace.applied": False, "thresholds.lmax": 52.0, "result": "기준 초과"}),
    dict(id="N-09", group="층간소음", payload=_noise(events=[_ev("2025-11-09T23:10", 53, 34),
                                                           _ev("2025-11-09T23:30", 53, 34)]),
         expect={"lmax_hits": 2, "result": "기준 이내"}),
    dict(id="N-10", group="층간소음", payload=_noise(events=[_ev("2025-11-09T23:10", 50, 37)]),
         expect={"result": "기준 초과", "exceeded_db": 3.0, "thresholds.leq": 34.0}),
    dict(id="N-11", group="층간소음",
         payload=_noise(noise_type="air", complex={"name": "새들마을 1단지", "approval_date": "2004-03-15"},
                        events=[_ev("2025-11-09T23:10", 0, 42)]),
         expect={"grace.applied": False, "thresholds.leq": 40.0, "result": "기준 초과"}),
    dict(id="N-12", group="층간소음",
         payload=_noise(noise_type="out_of_scope", sound_label="사람 목소리", events=[_ev("2025-11-09T23:10", 45, 33)]),
         expect={"result": "판정 범위 밖", "gate": "자동 처리"}),
    dict(id="N-13", group="층간소음",
         payload=_noise(confidence=0.62, events=[_ev("2025-11-09T23:10", 58, 37), _ev("2025-11-09T23:20", 58, 37),
                                                _ev("2025-11-09T23:30", 58, 37)]),
         expect={"result": "기준 초과", "gate": "보류"}),
    dict(id="N-14", group="층간소음",
         payload=_noise(message="죽여버리겠다", events=[_ev("2025-11-09T23:10", 58, 37),
                                                     _ev("2025-11-09T23:20", 58, 37),
                                                     _ev("2025-11-09T23:30", 58, 37)]),
         expect={"gate": "차단"}),
    dict(id="N-15", group="층간소음",
         payload=_noise(rag_citations=[], events=[_ev("2025-11-09T23:10", 58, 37)]),
         expect={"gate": "보류", "citations": []}),
    # ── 불법·이중주차
    dict(id="P-16", group="불법주차",
         payload={"kind": "parking", "case_id": "P-16", "zone": "fire",
                  "location": "지하 2층 B-27 소방자동차 전용구역", "shot_at": "2025-11-12T14:22",
                  "plate_ocr": "12가3456", "prior_violations_12m": 0, "confidence": 0.91},
         expect={"result": "위반 확인", "fine": 500000, "plate_masked": "12가****", "gate": "자동 처리"}),
    dict(id="P-17", group="불법주차",
         payload={"kind": "parking", "case_id": "P-17", "zone": "fire",
                  "location": "지하 2층 B-27 소방자동차 전용구역", "shot_at": "2025-11-13T09:05",
                  "plate_ocr": "34나7890", "prior_violations_12m": 1, "confidence": 0.94},
         expect={"fine": 1000000}),
    dict(id="P-18", group="불법주차",
         payload={"kind": "parking", "case_id": "P-18", "zone": "aisle", "location": "지하 2층 진입로 통로",
                  "shot_at": "2025-11-13T22:40", "plate_ocr": "56다1234", "prior_violations_12m": 0, "confidence": 0.88},
         expect={"fine": 0, "zone_label": "통로·진입로 이중주차"}),
    dict(id="P-19", group="불법주차",
         payload={"kind": "parking", "case_id": "P-19", "zone": "public_road", "location": "단지 앞 도로",
                  "shot_at": "2025-11-13T18:10", "plate_ocr": "78라5678", "prior_violations_12m": 0, "confidence": 0.9},
         expect={"fine": 0, "zone_label": "단지 외 도로 주정차", "citations.0.doc": "도로교통법"}),
    dict(id="P-20", group="불법주차",
         payload={"kind": "parking", "case_id": "P-20", "zone": "other_unit", "location": "지하 2층 302호 지정면",
                  "shot_at": "2025-11-12T20:15", "plate_ocr": "12가3456", "prior_violations_12m": 0, "confidence": 0.86},
         expect={"plate_masked": "12가****", "fine": 0, "zone_label": "타 세대 지정면 주차"}),
]


def _dig(obj, path):
    cur = obj
    for part in path.split("."):
        if isinstance(cur, list):
            cur = cur[int(part)]
        else:
            cur = cur.get(part) if isinstance(cur, dict) else None
    return cur


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_rule_case(case):
    result = R.evaluate(case["payload"])
    for path, want in case["expect"].items():
        got = _dig(result, path)
        if isinstance(want, (int, float)) and isinstance(got, (int, float)):
            assert abs(float(got) - float(want)) < 1e-9, f"{case['id']} {path}: 기대 {want} / 실측 {got}"
        else:
            assert got == want, f"{case['id']} {path}: 기대 {want} / 실측 {got}"


def test_all_20_cases_present():
    assert len(CASES) == 20


# ── 데모 프리셋(브리프 고정값) ────────────────────────────────
def test_demo_case3_preset():
    """케이스 3 — 23:20 · 최고 58 dB(A) · 3회 → 야간 기준 초과 +6 dB."""
    out = R.evaluate(_noise(events=[
        _ev("2026-11-22T23:20", 58, 37), _ev("2026-11-22T23:28", 57, 36), _ev("2026-11-22T23:40", 58, 37)]))
    assert out["result"] == "기준 초과"
    assert out["band"] == "야간"
    assert out["exceeded_db"] == 6.0
    assert out["severity"]["label"] == "기준 초과 · 주의"
    assert out["gate"] == "자동 처리"
    assert len(out["citations"]) == 3
    assert "302호 거주자님께" in out["nvc_letter"]
    assert "401호" in out["nvc_letter"]


def test_demo_case7_preset():
    """케이스 7 — 소방자동차 전용구역 → 50만 원 · 부과 권한 소방서."""
    out = R.evaluate({"kind": "parking", "zone": "fire", "location": "지하 2층 B-27 소방자동차 전용구역",
                      "shot_at": "2026-11-22T19:12", "plate_ocr": "12가3456", "confidence": 0.91, "shots": 2})
    assert out["fine"] == 500000
    assert out["fine_table"] == {"first": 500000, "repeat": 1000000}
    assert "관할 소방서" in out["boundary"]
    assert out["plate_masked"] == "12가****"
    assert "12가3456" not in out["nvc_letter"]


# ── 개인정보 마스킹 ─────────────────────────────────────────
@pytest.mark.parametrize("raw,want", [
    ("12가3456", "12가****"),
    ("12 가 3456", "12가****"),
    ("34나7890", "34나****"),
])
def test_mask_plate(raw, want):
    assert R.mask_plate(raw) == want


@pytest.mark.parametrize("raw,want", [
    ("401", "4**호"),
    ("105-401", "105동 4**호"),
    ("105동 401호", "105동 4**호"),
])
def test_mask_unit(raw, want):
    assert R.mask_unit(raw) == want


def test_mask_text():
    text = R.mask_text("105동 302호 앞 12가3456 차량, 연락처 010-9354-2951")
    assert "12가3456" not in text
    assert "010-9354-2951" not in text
    assert "12가****" in text


def test_standards_table():
    std = R.standards()
    rows = {(r["type"], r["metric"]): r for r in std["noise"]["rows"]}
    assert rows[("impact", "1분 등가소음도 Leq")]["night"] == 34.0
    assert rows[("impact", "1분 등가소음도 Leq")]["day"] == 39.0
    assert rows[("impact", "최고소음도 Lmax (1시간 3회)")]["night"] == 52.0
    assert std["parking"]["fire"]["first"] == 500000
    assert std["parking"]["fire"]["repeat"] == 1000000


def test_unknown_type_raises():
    with pytest.raises(ValueError):
        R.evaluate({"kind": "noise", "noise_type": "x", "events": [{"at": "2026-01-01T23:00", "lmax": 1, "leq": 1}]})
    with pytest.raises(ValueError):
        R.evaluate({"kind": "parking", "zone": "x"})
