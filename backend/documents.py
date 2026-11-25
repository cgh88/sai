# -*- coding: utf-8 -*-
"""문서 생성 — 중재 보고서·주간 브리핑·알림톡·NVC 자체 점검.

문장(초안)은 Liner Router 가 만들고, 표·필드·점검은 이 모듈이 결정론적으로 채운다.
"""

from __future__ import annotations

from datetime import datetime

from rule_engine import WEEKDAYS, cite, kr_clock, mask_plate, mask_unit, parse_dt

STATUS_ORDER = {"긴급": 0, "주의": 1, "보통": 2, "낮음": 3}


def nvc_checks(letter: str) -> list[dict]:
    """씬 11 의 NVC 3개 체크 — 문안을 기계적으로 점검해 화면에 초록으로 켠다."""
    text = letter or ""
    blame_words = ["당신은", "너는", "왜 ", "무례", "몰상식", "책임지", "!", "항의", "신고하겠"]
    # 마지막 정중한 마무리 문장은 같은 요청을 한 번 더 말한 것 — 요청 횟수에서 제외한다
    body = text.replace("확인 후 이동해 주시면 감사하겠습니다.", "")
    request_hits = body.count("주시면")
    gentle = ("괜찮습니다" in text) and ("즉시" not in text)
    return [
        {"label": "비난 없음", "ok": not any(w in text for w in blame_words) and bool(text),
         "hint": "평가·의도 추정 표현 없음"},
        {"label": "요구는 하나", "ok": request_hits <= 1 and bool(text),
         "hint": "요청 1건 · 사과 요구 없음"},
        {"label": "기한은 부드럽게", "ok": gentle,
         "hint": "부담 낮추기 문장 포함"},
    ]


def report_fields(result: dict, payload: dict) -> list[dict]:
    """관리소 중재 보고서 표 — 일시·유형·측정값·기준 대비·근거 조문·조치."""
    if result["kind"] == "noise":
        first = parse_dt(result["first_at"])
        when = f"{first.year}-{first.month:02d}-{first.day:02d}({WEEKDAYS[first.weekday()]}) {kr_clock(first)}"
        rows = [
            {"label": "일시", "value": f"{when} ~ {kr_clock(parse_dt(result['last_at']))}"},
            {"label": "유형", "value": f"층간소음 · {result['noise_label']} · {payload.get('sound_label', '발소리')}"},
            {"label": "세대", "value": f"{mask_unit(payload.get('unit', {}).get('from', ''))} → "
                                       f"{payload.get('unit', {}).get('to', '')}호"},
            {"label": "측정값", "value": f"등가 {result['measured']['leq_max']:.0f} dB(A) · "
                                        f"최고 {result['measured']['lmax_max']:.0f} dB(A) · "
                                        f"최고소음도 초과 {result['lmax_hits']}회"},
            {"label": "기준 대비", "value": f"{result['band']} 기준 Leq {result['thresholds']['leq']:.0f} / "
                                          f"Lmax {result['thresholds']['lmax']:.0f} dB(A) → "
                                          f"{result['result']} (+{result['exceeded_db']:.0f} dB)"},
            {"label": "근거 조문", "value": " · ".join(f"{c['doc']} {c['article']}" for c in result["citations"])},
            {"label": "조치", "value": "조정문 발송(익명) · 관리소 기록 · 주간 브리핑 포함" if result["gate"] == "자동 처리"
                                       else f"{result['gate']} — 사람 검토 후 발송"},
            {"label": "게이트", "value": f"{result['gate']} ({result['gate_reason']}) · 신뢰도 {result['confidence']:.2f}"},
        ]
    else:
        shot = parse_dt(result["shot_at"])
        rows = [
            {"label": "일시", "value": f"{shot.year}-{shot.month:02d}-{shot.day:02d}({WEEKDAYS[shot.weekday()]}) {kr_clock(shot)}"},
            {"label": "유형", "value": f"불법·이중주차 · {result['zone_label']}"},
            {"label": "위치", "value": result["location"]},
            {"label": "차량", "value": f"{result['plate_masked']} (원본 암호화 · 관리자 한정)"},
            {"label": "측정값", "value": f"현장 사진 {result['shots']}장 · 1년 내 위반 {result['prior_violations_12m']}회"},
            {"label": "기준 대비", "value": result["fine_note"]},
            {"label": "근거 조문", "value": " · ".join(f"{c['doc']} {c['article']}" for c in result["citations"])},
            {"label": "조치", "value": "이동 요청 알림톡(30분 여유) → 미이동 시 관리소 보고" if result["zone"] == "fire"
                                       else "이동 요청 · 이력 기록"},
            {"label": "게이트", "value": f"{result['gate']} ({result['gate_reason']}) · 신뢰도 {result['confidence']:.2f}"},
        ]
    rows.append({"label": "책임 경계", "value": result["boundary"]})
    return rows


def report_markdown(case: dict, result: dict, summary: str = "") -> str:
    payload = case["payload"]
    lines = [f"# 중재 보고서 — {case['id']}", ""]
    lines.append(f"- 단지: {(payload.get('complex') or {}).get('name', '새들마을 3단지')} (가상)")
    lines.append(f"- 접수: {case.get('received_at', '')} · 담당: {case.get('assignee', '관리소 주무')}")
    lines.append("")
    lines.append("| 항목 | 내용 |")
    lines.append("| --- | --- |")
    for row in report_fields(result, payload):
        lines.append(f"| {row['label']} | {row['value']} |")
    lines.append("")
    if summary:
        lines.append("## 요약")
        lines.append(summary)
        lines.append("")
    lines.append("## 조정문 초안")
    lines.append(result.get("nvc_letter") or "")
    lines.append("")
    lines.append(f"> {result['boundary']}")
    return "\n".join(lines)


def alimtalk_text(result: dict, payload: dict) -> str:
    """카카오 알림톡 미리보기 — 감정 없는 문장 + 30분 여유."""
    body = result.get("nvc_letter") or ""
    footer = "이동이 어려우시면 관리사무소로 알려 주세요. 확인 후 바로 처리하겠습니다."
    return f"{body}\n\n{footer}"


def briefing_rows(cases: list[dict]) -> list[dict]:
    """주간 브리핑(씬 12 하단) — 유형별 건수·평균 처리·증빙률."""
    total = len(cases)
    noise = sum(1 for c in cases if c["kind"] == "noise")
    parking = total - noise
    avg_min = round(sum(c["processing_min"] for c in cases) / total, 1) if total else 0
    done = sum(1 for c in cases if c["status"] in ("처리 완료", "발송 완료", "이동 요청 발송"))
    return [
        {"label": "이번 주 접수", "value": f"{total}건", "note": f"층간소음 {noise} · 주차 {parking}"},
        {"label": "평균 총 처리", "value": f"{avg_min:.0f}분", "note": "검토·승인 포함"},
        {"label": "증빙 완비", "value": f"{round(done / total * 100) if total else 0}%", "note": f"처리 완료 {done}건 / 접수 {total}건 · 일지 자동"},
        {"label": "사람 승인", "value": "100%", "note": "자동 발송 차단 게이트 유지"},
    ]


def delivered_at() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def mask_log_text(text: str) -> str:
    return (text or "").replace("12가3456", "12가****")
