# -*- coding: utf-8 -*-
"""프롬프트·검색 질의 — 2단 신뢰 구조에서 LLM 이 하는 일을 '문장'으로 한정한다."""

from __future__ import annotations

from rule_engine import cite, mask_unit

LETTER_SYSTEM = """당신은 공동주택 관리사무소의 갈등 조정 문안 작성 보조입니다.
아래 규칙을 반드시 지킵니다.
1) 비폭력대화(NVC) 4단계 순서로만 씁니다: ① 관찰(사실·수치·시각) ② 영향과 필요 ③ 요청(하나만) ④ 부담 낮추기.
2) 비난·평가·의도 추정·명령·위협·법적 위협 표현을 쓰지 않습니다. '당신은 ~했다' 대신 '~한 소리가 들렸습니다'처럼 사실만 적습니다.
3) 요청은 한 문장, 하나만. 사과를 요구하지 않습니다.
4) 신고자와 발생 세대의 신원(이름·연락처·동호수 전체)을 드러내지 않습니다. 수신 호수는 '302호 거주자님'까지만 씁니다.
5) 주어진 판정 결과와 인용 근거에 없는 숫자·조문을 새로 만들지 않습니다.
6) 200~320자, 존댓말, 인사말·서명 없이 본문만 출력합니다. 머리말·설명·따옴표를 붙이지 않습니다."""


def noise_query(result: dict, payload: dict) -> str:
    return (
        f"공동주택 층간소음 {result['band']} 기준: {result['noise_label']} 소음 "
        f"{result['thresholds']['window']} 등가소음도 기준 {result['thresholds']['leq']:.0f} dB(A)"
        + (f", 최고소음도 기준 {result['thresholds']['lmax']:.0f} dB(A) (1시간 내 3회 이상 초과 시 기준 초과)"
           if result["thresholds"]["lmax"] else "")
        + ". 공동주택관리법 제20조(층간소음 기준 초과 시 관리주체의 조치)의 내용, "
        "그리고 공동주택 관리규약의 생활소음(야간 22시~06시) 관련 조항. "
        "기준 대조 방법과 관리주체의 조치·기록 의무를 조문 근거와 함께 알려줘."
    )


def parking_query(result: dict, payload: dict) -> str:
    zone = result["zone_label"]
    if result["zone"] == "fire":
        return (
            "소방자동차 전용구역에 주차하는 행위의 금지 근거(소방기본법 제21조의2 제2항)와 "
            "그 과태료 금액(소방기본법 제56조 제3항 및 시행령 별표 3 — 1회 50만 원, 1년 내 2회 이상 100만 원), "
            "부과 권한이 있는 기관. 그리고 공동주택 관리규약의 주차질서 조항. 조문 근거와 함께 알려줘."
        )
    if result["zone"] == "public_road":
        return (
            "공동주택 단지 밖 도로의 주정차 위반 근거(도로교통법 제32조)와 주차장법 제6조, "
            "신고·단속 주체. 조문 근거와 함께 알려줘."
        )
    return (
        f"공동주택 단지 내 '{zone}'의 근거: 공동주택관리법 제18조(관리규약)와 관리규약의 주차질서 조항, "
        "과태료 규정이 있는지, 관리주체의 이동 요청·기록 의무. 조문 근거와 함께 알려줘."
    )


def letter_user_prompt(result: dict, payload: dict, evidence_text: str = "") -> str:
    unit_to = (payload.get("unit") or {}).get("to", "")
    unit_from = (payload.get("unit") or {}).get("from", "")
    citations = "\n".join(f"- {cite(c)}" for c in result.get("citations", []))
    if result["kind"] == "noise":
        facts = (
            f"- 단지: {(payload.get('complex') or {}).get('name', '')}\n"
            f"- 신고 세대 → 발생 세대: {mask_unit(unit_from)} → {mask_unit(unit_to)}\n"
            f"- 소리: {payload.get('sound_label', '발소리')} ({result['noise_label']})\n"
            f"- 시간대: {result['band']} / 측정 {result.get('first_at', '')} ~ {result.get('last_at', '')}\n"
            f"- 측정: 등가 {result['measured']['leq_max']:.0f} dB(A) vs 기준 {result['thresholds']['leq']:.0f} dB(A), "
            f"최고 {result['measured']['lmax_max']:.0f} dB(A) vs 기준 "
            f"{result['thresholds']['lmax'] if result['thresholds']['lmax'] else '-'} dB(A), "
            f"최고소음도 초과 {result['lmax_hits']}회, 지속 {payload.get('duration_min', 20)}분\n"
            f"- 판정(엔진 확정): {result['result']} ({result['severity']['label']})\n"
            f"- 신고자 상황: {payload.get('household_context', '')}\n"
            f"- 희망 요청: {payload.get('request', '')}"
        )
    else:
        facts = (
            f"- 단지: {(payload.get('complex') or {}).get('name', '')}\n"
            f"- 위치: {result['location']} ({result['zone_label']})\n"
            f"- 확인 시각: {result['shot_at']}\n"
            f"- 차량번호(마스킹): {result['plate_masked']}\n"
            f"- 판정(엔진 확정): {result['result']} · {result['fine_note']}\n"
            f"- 조치 권한: {result['authority']}"
        )
    return (
        "다음은 판정 엔진이 numeric 으로 확정한 사실입니다. 이 사실만으로 NVC 조정문을 작성하세요.\n\n"
        f"{facts}\n\n인용 근거:\n{citations}\n\n"
        + (f"법령 검색 요약(참고, 새 숫자를 만들지 말 것):\n{evidence_text[:1200]}\n\n" if evidence_text else "")
        + "출력: 본문만."
    )


REPORT_SYSTEM = """당신은 공동주택 관리사무소의 중재 보고서 요약 보조입니다.
주어진 판정 결과와 근거만 사용해 3~4문장의 한국어 요약을 씁니다.
숫자·조문·금액을 새로 만들지 말고, 처분 권한이 관리주체·소방서 등에 있음을 한 번 밝힙니다.
머리말 없이 요약문만 출력합니다."""


def report_user_prompt(result: dict, payload: dict) -> str:
    citations = "\n".join(f"- {cite(c)}" for c in result.get("citations", []))
    if result["kind"] == "noise":
        head = (
            f"접수 {payload.get('case_id', '')} · 층간소음 · {result['band']} · "
            f"등가 {result['measured']['leq_max']:.0f} dB(A)(기준 {result['thresholds']['leq']:.0f}), "
            f"최고 {result['measured']['lmax_max']:.0f} dB(A)(기준 {result['thresholds']['lmax']}), "
            f"판정 {result['result']} · 게이트 {result['gate']}"
        )
    else:
        head = (
            f"접수 {payload.get('case_id', '')} · {result['zone_label']} · {result['location']} · "
            f"{result['plate_masked']} · {result['fine_note']} · 판정 {result['result']} · 게이트 {result['gate']}"
        )
    return f"{head}\n\n인용 근거:\n{citations}\n\n3~4문장 요약만 출력하세요."
