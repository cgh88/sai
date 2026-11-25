#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""「사이(Sai)」 1단 결정론적 룰 엔진.

설계 원칙: "숫자는 코드가, 문장은 모델이, 최종 결정은 사람이."

  · 수치 비교(법령 기준 대조)는 이 엔진이 결정론적으로 확정한다(감사 가능, LLM 아님).
  · 2단(LLM)은 이 엔진이 확정한 사실·기준·게이트를 받아서 문장만 만든다.
  · 근거 인용(법령·규약)과 신뢰도·위협 표현 게이트를 통과해야 자동 처리가 진행된다.
  · 판정은 '판단 보조'이며 최종 판단·처분은 관리주체·지자체·법원의 권한이다.

기준 출처
  · 「공동주택 층간소음의 범위와 기준에 관한 규칙」 제3조 및 별표 (2023. 1. 2. 개정)
  · 「소방기본법」 제21조의2 제2항 / 제56조 제3항 및 시행령 별표 3 (과태료 1회 50만 원, 1년 내 2회부터 100만 원)
  · 「공동주택관리법」 제18조(관리규약) · 제20조(층간소음 기준 초과 시 관리주체의 조치)
  · 「도로교통법」 제32조, 「주차장법」 제6조, 「경범죄 처벌법」 제3조 제1항 제26호

이 모듈은 외부 패키지에 의존하지 않는다(표준 라이브러리만).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

ENGINE_NAME = "sai-rule-engine"
ENGINE_VERSION = "1.0.0"

# ────────────────────────────────────────────────────────────────
# 1. 기준 테이블
# ────────────────────────────────────────────────────────────────
NOISE_STD = {
    "impact": {
        "label": "직접충격",
        "leq": {"주간": 39.0, "야간": 34.0},      # 1분 등가소음도
        "lmax": {"주간": 57.0, "야간": 52.0},     # 최고소음도 (1시간 내 3회 이상 초과 시 기준 초과)
        "lmax_hits_required": 3,
        "window_min": 60,
        "leq_window": "1분",
    },
    "air": {
        "label": "공기전달",
        "leq": {"주간": 45.0, "야간": 40.0},      # 5분 등가소음도
        "lmax": None,
        "lmax_hits_required": None,
        "window_min": 60,
        "leq_window": "5분",
    },
}

GRACE = {
    # 2005. 6. 30. 이전 사업승인 단지는 2025. 1. 1.부터 직접충격 기준 +2 dB(A)
    "approval_before": "2005-06-30",
    "effective_from": "2025-01-01",
    "delta_db": 2.0,
    "applies_to": ("impact",),
}

GATES = {"confidence_min": 0.70, "citation_min": 1}

THREAT_PATTERNS = [
    "죽여", "죽인다", "죽을", "고소", "가만두지", "칼로", "때려", "부숴",
    "신고해버", "경찰에", "복수", "보복",
]

CITATION_NOISE = {
    "doc": "공동주택 층간소음의 범위와 기준에 관한 규칙",
    "article": "제3조 및 별표",
    "effective": "2023-01-02",
    "source": "국가법령정보센터",
}
CITATION_NOISE_LAW = {
    "doc": "공동주택관리법",
    "article": "제20조",
    "effective": "2024-07-01",
    "source": "국가법령정보센터",
}
CITATION_MGMT_RULES = {
    "doc": "새들마을 3단지 관리규약",
    "article": "제12조(주차질서) · 제18조(층간소음)",
    "effective": "2025-03-01",
    "source": "단지 관리규약(입주자대표회의 의결본)",
}
CITATION_MGMT_LAW_18 = {
    "doc": "공동주택관리법",
    "article": "제18조(관리규약)",
    "effective": "2024-07-01",
    "source": "국가법령정보센터",
}
CITATION_FIRE_1 = {
    "doc": "소방기본법",
    "article": "제21조의2 제2항",
    "effective": "2024-01-01",
    "source": "국가법령정보센터",
}
CITATION_FIRE_2 = {
    "doc": "소방기본법",
    "article": "제56조 제3항 및 시행령 별표 3",
    "effective": "2024-01-01",
    "source": "국가법령정보센터",
}
CITATION_TRAFFIC = {"doc": "도로교통법", "article": "제32조", "effective": "2024-01-01", "source": "국가법령정보센터"}
CITATION_PARKING_LAW = {
    "doc": "주차장법",
    "article": "제6조(주차장의 구조·설비기준)",
    "effective": "2023-12-21",
    "source": "국가법령정보센터",
}
CITATION_MINOR_OFFENSE = {
    "doc": "경범죄 처벌법",
    "article": "제3조 제1항 제26호(소음 등)",
    "effective": "2023-07-04",
    "source": "국가법령정보센터",
}

PARKING_ZONES = {
    "fire": {
        "label": "소방자동차 전용구역",
        "citations": [CITATION_FIRE_1, CITATION_FIRE_2, CITATION_MGMT_RULES],
        "penalty": True,
        "authority": "관할 소방서",
        "urgency": "긴급",
    },
    "aisle": {
        "label": "통로·진입로 이중주차",
        "citations": [CITATION_MGMT_RULES, CITATION_MGMT_LAW_18],
        "penalty": False,
        "authority": "관리사무소",
        "urgency": "보통",
    },
    "stall_intrusion": {
        "label": "구획 침범·이중주차",
        "citations": [CITATION_MGMT_RULES, CITATION_MGMT_LAW_18],
        "penalty": False,
        "authority": "관리사무소",
        "urgency": "보통",
    },
    "other_unit": {
        "label": "타 세대 지정면 주차",
        "citations": [CITATION_MGMT_RULES, CITATION_MGMT_LAW_18],
        "penalty": False,
        "authority": "관리사무소",
        "urgency": "낮음",
    },
    "public_road": {
        "label": "단지 외 도로 주정차",
        "citations": [CITATION_TRAFFIC, CITATION_PARKING_LAW],
        "penalty": False,
        "authority": "관할 지자체·경찰서",
        "urgency": "보통",
    },
}

FIRE_FINE = {"first": 500000, "repeat": 1000000}   # 1회 50만 원, 1년 내 2회부터 100만 원

WEEKDAYS = ("월", "화", "수", "목", "금", "토", "일")

BOUNDARY_NOISE = "판단 보조 도구 — 최종 판단·처분은 관리주체·지자체·법원의 권한"
BOUNDARY_PARKING = "신고·과태료 부과는 「사이」의 권한 밖 — 판단 보조 도구이며 최종 처분은 {authority}의 권한"


# ────────────────────────────────────────────────────────────────
# 2. 유틸 (일시·마스킹·문장)
# ────────────────────────────────────────────────────────────────
def parse_dt(value) -> datetime:
    """'2026-11-22T23:20' / '2026-11-22 23:20' / '2026-11-22' / datetime → datetime."""
    if isinstance(value, datetime):
        return value
    text = str(value).strip().replace("T", " ")
    if text.endswith("Z"):
        text = text[:-1]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:len("2026-11-22 23:20:00")], fmt)
        except ValueError:
            continue
    raise ValueError(f"해석할 수 없는 일시: {value!r}")


def parse_date(value):
    return parse_dt(value).date()


def time_band(moment: datetime) -> str:
    """주간 06:00~22:00 / 야간 22:00~06:00 (경계는 시작 시각에 포함)."""
    minute = moment.hour * 60 + moment.minute
    return "야간" if (minute >= 22 * 60 or minute < 6 * 60) else "주간"


def kr_clock(moment: datetime, with_period: bool = True) -> str:
    h, m = moment.hour, moment.minute
    if h >= 18:
        period, hh = "밤", h - 12
    elif h >= 12:
        period, hh = "오후", h - 12
    elif h >= 6:
        period, hh = "오전", h
    else:
        period, hh = "새벽", h
    body = f"{hh}시" if m == 0 else f"{hh}시 {m}분"
    return f"{period} {body}" if with_period else body


def mask_plate(plate: str) -> str:
    """차량번호 즉시 마스킹 — 앞 숫자 2자리와 한글만 남기고 뒤 숫자 4자리는 가린다.

    '12가3456' → '12가****'   '12 가 3456' → '12가****'
    """
    if not plate:
        return ""
    compact = re.sub(r"\s+", "", str(plate))
    digits = [i for i, ch in enumerate(compact) if ch.isdigit()]
    if len(digits) < 3:
        return compact[:2] + "****"
    cut = digits[2]          # 세 번째 숫자부터 가린다
    return compact[:cut] + "*" * (len(compact) - cut)


def mask_unit(unit: str) -> str:
    """세대 표기 마스킹: '105-401' → '105동 4**호', '401' → '4**호'."""
    if not unit:
        return ""
    text = str(unit).strip()
    if re.fullmatch(r"\d{3,4}", text):          # '401' → '4**호'
        return f"{text[0]}{'*' * (len(text) - 1)}호"
    match = re.match(r"^(\d{1,3})\s*[-동]\s*(\d{1,4})(호)?$", text)
    if not match:
        return text[:2] + "**" if len(text) > 2 else text
    dong, ho = match.group(1), match.group(2)
    masked_ho = (ho[0] + "*" * (len(ho) - 1)) if len(ho) > 1 else ho
    return f"{dong}동 {masked_ho}호" if match.group(0).find("-") >= 0 or "동" in text else f"{masked_ho}호"


def mask_text(text: str) -> str:
    """자유 문장에서 차량번호·전화번호·세대 표기를 가린다(로그·대시보드 표시용)."""
    if not text:
        return ""
    out = re.sub(r"\b\d{2,3}\s?[가-힣]\s?\d{4}\b", lambda m: mask_plate(m.group(0)), text)
    out = re.sub(r"\b01[016789][-.\s]?\d{3,4}[-.\s]?\d{4}\b", "010-****-****", out)
    out = re.sub(r"\b(\d{1,3})동\s?(\d{1,4})호", lambda m: f"{m.group(1)}동 {m.group(2)[0]}**호", out)
    return out


def money(won: int) -> str:
    return f"{won // 10000}만 원"


def has_threat(text: str):
    if not text:
        return None
    for pattern in THREAT_PATTERNS:
        if pattern in text:
            return pattern
    return None


def mgmt_rules(payload: dict) -> dict:
    """단지 이름이 바뀌면 인용 카드의 문서명도 함께 바뀐다."""
    name = (payload.get("complex") or {}).get("name") or CITATION_MGMT_RULES["doc"].replace(" 관리규약", "")
    return {**CITATION_MGMT_RULES, "doc": f"{name} 관리규약"}


def cite(c: dict) -> str:
    return f"「{c['doc']}」 {c['article']} (시행 {c['effective']})"


# ────────────────────────────────────────────────────────────────
# 3. 층간소음 판정
# ────────────────────────────────────────────────────────────────
def noise_thresholds(noise_type: str, band: str, approval_date, measured_date):
    """유형·시간대·사업승인일·측정일로 적용 기준을 확정한다(경과규정 자동 분기)."""
    std = NOISE_STD[noise_type]
    leq = std["leq"][band]
    lmax = std["lmax"][band] if std["lmax"] else None
    grace = {"applied": False, "delta_db": 0.0, "reason": "경과규정 대상 아님"}
    if noise_type in GRACE["applies_to"] and approval_date and measured_date:
        early = approval_date <= parse_date(GRACE["approval_before"])
        if not early:
            grace["reason"] = (
                f"사업승인일 {approval_date.isoformat()} — "
                f"{GRACE['approval_before']} 이후 승인으로 경과규정 미적용"
            )
        elif measured_date < parse_date(GRACE["effective_from"]):
            grace["reason"] = (
                f"측정일 {measured_date.isoformat()} — {GRACE['effective_from']} 이전으로 경과규정 미적용"
            )
        else:
            grace.update(
                applied=True,
                delta_db=GRACE["delta_db"],
                reason=(
                    f"사업승인일 {approval_date.isoformat()} — {GRACE['approval_before']} 이전 승인 단지로 "
                    f"{GRACE['effective_from']}부터 +{GRACE['delta_db']:.0f} dB(A) 적용"
                ),
            )
            leq += GRACE["delta_db"]
            lmax = lmax + GRACE["delta_db"] if lmax is not None else None
    return {"leq": round(leq, 1), "lmax": (round(lmax, 1) if lmax is not None else None), "grace": grace}


def severity_of(exceeded: bool, exceed_db: float) -> dict:
    """±3 dB 앱 측정 오차를 감안해 '초과'와 '초과 의심'을 나눈다(부록 G 방어 논리)."""
    if not exceeded:
        return {"level": "이내", "label": "기준 이내", "tone": "ok"}
    if exceed_db >= 3.0:
        return {"level": "초과", "label": "기준 초과 · 주의", "tone": "danger"}
    return {"level": "의심", "label": "기준 초과 의심 · 확인 필요", "tone": "warn"}


def evaluate_noise(payload: dict) -> dict:
    events = payload.get("events") or []
    if not events:
        raise ValueError("events(측정값)가 필요합니다.")
    events = sorted(events, key=lambda e: parse_dt(e["at"]))
    stamps = [parse_dt(e["at"]) for e in events]
    band = time_band(stamps[0])
    mixed_band = len({time_band(s) for s in stamps}) > 1

    complex_info = payload.get("complex") or {}
    approval = parse_date(complex_info["approval_date"]) if complex_info.get("approval_date") else None
    measured = parse_date(payload.get("measured_date") or stamps[0].date().isoformat())

    rules = ["R1"]          # 시간대 경계 판정
    noise_type = payload.get("noise_type", "impact")

    # R5 — 규칙상 범위 밖(사람 목소리·인테리어·급배수 등)
    if noise_type == "out_of_scope":
        return {
            "case_id": payload.get("case_id", ""),
            "kind": "noise",
            "noise_type": noise_type,
            "noise_label": "규칙 범위 밖",
            "band": band,
            "mixed_band": mixed_band,
            "result": "판정 범위 밖",
            "severity": {"level": "범위밖", "label": "판정 범위 밖", "tone": "muted"},
            "gate": "자동 처리",
            "gate_reason": "층간소음 규칙 적용 대상 아님 — 안내로 전환",
            "rules_fired": rules + ["R5"],
            "citations": [CITATION_MINOR_OFFENSE, mgmt_rules(payload)],
            "confidence": float(payload.get("confidence", 1.0)),
            "guidance": (
                "생활소음(사람 목소리·인테리어·급배수)은 「공동주택 층간소음의 범위와 기준에 관한 규칙」의 "
                "적용 대상이 아니다 — 「경범죄 처벌법」·관리규약·공사 동의 절차로 안내한다."
            ),
            "boundary": BOUNDARY_NOISE,
            "nvc_letter": None,
        }

    if noise_type not in NOISE_STD:
        raise ValueError(f"알 수 없는 소음 유형: {noise_type!r} (impact·air·out_of_scope)")

    std = noise_thresholds(noise_type, band, approval, measured)
    if std["grace"]["applied"]:
        rules.append("R2")      # 경과규정 +2 dB 자동 적용

    lmax_max = max((float(e.get("lmax") or 0) for e in events), default=0.0)
    leq_max = max((float(e.get("leq") or 0) for e in events), default=0.0)

    # R3 — 최고소음도: 1시간 내 3회 이상 초과
    hit_count = 0
    window = NOISE_STD[noise_type]["window_min"]
    if std["lmax"] is not None:
        for i, base in enumerate(stamps):
            hits = [
                j for j, s in enumerate(stamps)
                if s >= base and (s - base) <= timedelta(minutes=window)
                and float(events[j].get("lmax") or 0) > std["lmax"]
            ]
            hit_count = max(hit_count, len(hits))
        rules.append("R3")
    lmax_exceeded = std["lmax"] is not None and hit_count >= NOISE_STD[noise_type]["lmax_hits_required"]

    # R4 — 등가소음도 기준
    leq_exceeded = leq_max > std["leq"]
    rules.append("R4")

    exceeded = bool(lmax_exceeded or leq_exceeded)
    reasons = []
    if lmax_exceeded:
        reasons.append(
            f"최고소음도 {lmax_max:.0f} dB(A) — {band} 기준 {std['lmax']:.0f} dB(A)를 "
            f"1시간 내 {hit_count}회 초과"
        )
    if leq_exceeded:
        reasons.append(
            f"{NOISE_STD[noise_type]['leq_window']} 등가소음도 {leq_max:.0f} dB(A) — "
            f"{band} 기준 {std['leq']:.0f} dB(A) 초과"
        )
    if not exceeded:
        if std["lmax"] is not None and hit_count:
            reasons.append(f"최고소음도 초과 {hit_count}회 — 기준(1시간 내 3회 이상)에 미달")
        else:
            reasons.append("최고·평균 소음도 모두 기준 이내")
        if std["grace"]["applied"]:
            reasons.append(f"경과규정 +{GRACE['delta_db']:.0f} dB(A) 적용 기준")

    exceed_db = (
        round(max(lmax_max - (std["lmax"] or 0), leq_max - std["leq"]), 1) if exceeded else 0.0
    )

    # 규칙 별표 · 관리법 제20조 · 단지 관리규약(제18조) — 신고 1건이면 항상 세 갈래로 근거를 붙인다
    citations = [CITATION_NOISE, CITATION_NOISE_LAW, mgmt_rules(payload)]
    # RAG 검색이 조문을 하나도 돌려주지 못한 경우를 재현할 수 있게 한다
    if payload.get("rag_citations") is not None:
        citations = list(payload["rag_citations"])

    # 게이트: ① 인용 0건 → 보류 ② 신뢰도 < 0.7 → 보류 ③ 위협 표현 → 자동 발송 차단
    gate, gate_reason = "자동 처리", "게이트 통과"
    if not citations:
        rules.append("R8")
        gate, gate_reason = "보류", "근거 인용 0건 — 판정 보류(확인 필요)"
    elif float(payload.get("confidence", 1.0)) < GATES["confidence_min"]:
        rules.append("R6")
        gate = "보류"
        gate_reason = (
            f"신뢰도 {float(payload['confidence']):.2f} < 임계값 {GATES['confidence_min']:.2f} — 관리소 검토 대기열"
        )
    threat = has_threat(payload.get("message", ""))
    if threat:
        rules.append("R7")
        gate, gate_reason = "차단", f"위협 표현('{threat}') 감지 — 자동 발송 차단"

    result = {
        "case_id": payload.get("case_id", ""),
        "kind": "noise",
        "noise_type": noise_type,
        "noise_label": NOISE_STD[noise_type]["label"],
        "sound_label": payload.get("sound_label", "발소리"),
        "band": band,
        "mixed_band": mixed_band,
        "thresholds": {"leq": std["leq"], "lmax": std["lmax"], "band": band, "window": NOISE_STD[noise_type]["leq_window"]},
        "measured": {"leq_max": round(leq_max, 1), "lmax_max": round(lmax_max, 1)},
        "margin": {
            "leq": round(leq_max - std["leq"], 1),
            "lmax": (round(lmax_max - std["lmax"], 1) if std["lmax"] is not None else None),
            "pressure_ratio": round(10 ** (exceed_db / 20), 2) if exceed_db else 1.0,
        },
        "grace": std["grace"],
        "lmax_hits": hit_count,
        "result": "기준 초과" if exceeded else "기준 이내",
        "severity": severity_of(exceeded, exceed_db),
        "exceeded_db": exceed_db,
        "reasons": reasons,
        "gate": gate,
        "gate_reason": gate_reason,
        "rules_fired": rules,
        "citations": citations,
        "confidence": float(payload.get("confidence", 1.0)),
        "boundary": BOUNDARY_NOISE,
        "measurement_note": "앱 측정값 — ±3 dB 오차를 감안해 '초과/초과 의심'을 구분하며, 정밀 측정은 이웃사이센터 현장진단",
        "unit": payload.get("unit", {}),
        "first_at": stamps[0].isoformat(timespec="minutes"),
        "last_at": stamps[-1].isoformat(timespec="minutes"),
    }
    result["nvc_letter"] = nvc_letter_noise(payload, result)
    result["nvc_request"] = payload.get("request", "이 시간대에는 소리를 조금 낮춰 주시면")
    return result


def nvc_letter_noise(payload: dict, res: dict) -> str:
    """NVC 4단계(사실–영향·필요–요청–부담 낮추기) 조정문. 의도 추정 배제, 요청은 하나로."""
    events = payload.get("events") or []
    first = parse_dt(events[0]["at"])
    last = parse_dt(events[-1]["at"])
    to = (payload.get("unit") or {}).get("to", "")
    src = (payload.get("unit") or {}).get("from", "")
    sound = payload.get("sound_label", "발소리")
    date_txt = f"{first.month}월 {first.day}일({WEEKDAYS[first.weekday()]})"
    same_period = kr_clock(last).split()[0] == kr_clock(first).split()[0]
    span = f"{date_txt} {kr_clock(first)}부터 {kr_clock(last, with_period=not same_period)}까지"
    context = payload.get("household_context", "")
    request = payload.get("request", "이 시간대에는 소리를 조금 낮춰 주시면")
    src_txt = f"{src}호에서 " if src else ""

    if res["result"] == "기준 초과" and res["thresholds"]["lmax"]:
        head = (
            f"{to}호 거주자님께 — 지난 {span} {src_txt}{sound}로 추정되는 소리가 반복되었습니다. "
            f"최고소음도는 {res['measured']['lmax_max']:.0f} dB(A)로 {res['band']} 기준"
            f"({res['thresholds']['lmax']:.0f} dB(A))을 넘는 순간이 1시간 내 {res['lmax_hits']}회 이상 있었습니다."
        )
    elif res["result"] == "기준 초과":
        head = (
            f"{to}호 거주자님께 — 지난 {span} {src_txt}{sound}로 추정되는 소리가 반복되었습니다. "
            f"{res['thresholds']['window']} 등가소음도는 {res['measured']['leq_max']:.0f} dB(A)로 "
            f"{res['band']} 기준({res['thresholds']['leq']:.0f} dB(A))을 넘었습니다."
        )
    else:
        threshold_txt = f"{res['thresholds']['lmax']:.0f} dB(A)"
        if res["grace"]["applied"]:
            threshold_txt += f", 경과규정 +{res['grace']['delta_db']:.0f} dB(A) 적용"
        head = (
            f"{to}호 거주자님께 — 지난 {span} {src_txt}{sound}로 추정되는 소리가 들렸습니다. "
            f"측정된 최고소음도는 {res['measured']['lmax_max']:.0f} dB(A)로, 이 단지에 적용되는 {res['band']} "
            f"기준({threshold_txt})에는 이르지 않았습니다. 기준 초과로 판정된 사안이 아니라는 점을 먼저 말씀드립니다."
        )

    parts = [head]
    if context:
        parts.append(context)
    parts.append("소리가 나쁜 마음에서였다고는 생각하지 않습니다.")
    lead = "다만 이 시간대만큼은 " if not request.startswith("이 시간대") else "다만 "
    parts.append(f"{lead}{request} 저희가 훨씬 편안해질 것 같습니다.")
    parts.append("바로 답을 주지 않으셔도 괜찮습니다.")
    return " ".join(parts)


# ────────────────────────────────────────────────────────────────
# 4. 불법·이중주차 판정
# ────────────────────────────────────────────────────────────────
def evaluate_parking(payload: dict) -> dict:
    zone_key = payload.get("zone", "aisle")
    if zone_key not in PARKING_ZONES:
        raise ValueError(f"알 수 없는 주차 구역: {zone_key!r}")
    zone = dict(PARKING_ZONES[zone_key])
    zone["citations"] = [mgmt_rules(payload) if c is CITATION_MGMT_RULES else c for c in zone["citations"]]
    rules = ["R12"] if payload.get("plate_ocr") else []

    citations = list(zone["citations"])
    if payload.get("rag_citations") is not None:
        citations = list(payload["rag_citations"])
    fine = 0
    fine_note = ""
    if zone["penalty"]:
        rules += ["R9"]
        prior = int(payload.get("prior_violations_12m", 0) or 0)
        fine = FIRE_FINE["repeat"] if prior >= 1 else FIRE_FINE["first"]
        fine_note = (
            f"{'1년 내 2회 이상' if prior >= 1 else '1년 내 1회'} — 과태료 {money(fine)}"
            f" · 부과 권한: {zone['authority']}"
        )
    elif zone_key == "public_road":
        rules += ["R11"]
        fine_note = f"단지 외 도로 주정차 — {zone['authority']} 소관"
    else:
        rules += ["R10"]
        fine_note = f"과태료 규정 없음 — 관리규약에 따른 이동 요청·기록 대상 · 조치 주체: {zone['authority']}"

    # 게이트
    gate, gate_reason = "자동 처리", "게이트 통과"
    if not citations:
        gate, gate_reason = "보류", "근거 인용 0건 — 판정 보류(확인 필요)"
    elif float(payload.get("confidence", 1.0)) < GATES["confidence_min"]:
        gate = "보류"
        gate_reason = (
            f"신뢰도 {float(payload['confidence']):.2f} < 임계값 {GATES['confidence_min']:.2f} — 관리소 검토 대기열"
        )

    shot = parse_dt(payload.get("shot_at", "2026-01-01 12:00"))
    res = {
        "case_id": payload.get("case_id", ""),
        "kind": "parking",
        "zone": zone_key,
        "zone_label": zone["label"],
        "location": payload.get("location", ""),
        "shot_at": shot.isoformat(timespec="minutes"),
        "plate_masked": mask_plate(payload.get("plate_ocr", "")),
        "prior_violations_12m": int(payload.get("prior_violations_12m", 0) or 0),
        "shots": int(payload.get("shots", 1) or 1),
        "result": "위반 확인",
        "severity": {
            "level": "긴급" if zone_key == "fire" else "주의",
            "label": "즉시 이동 요청 대상" if zone_key == "fire" else "이동 요청 대상",
            "tone": "danger" if zone_key == "fire" else "warn",
        },
        "urgency": zone["urgency"],
        "fine": fine,
        "fine_note": fine_note,
        "fine_table": FIRE_FINE if zone["penalty"] else None,
        "authority": zone["authority"],
        "reasons": [fine_note],
        "gate": gate,
        "gate_reason": gate_reason,
        "rules_fired": rules,
        "citations": citations,
        "confidence": float(payload.get("confidence", 1.0)),
        "boundary": BOUNDARY_PARKING.format(authority=zone["authority"]),
    }
    res["nvc_letter"] = nvc_letter_parking(payload, res)
    res["nvc_request"] = (
        "차량을 다른 정식 구획으로 옮겨 주시면" if zone_key == "fire"
        else "차량을 지정된 구획으로 옮겨 주시면" if zone_key in ("aisle", "stall_intrusion")
        else "차량을 본인 지정면이나 방문객 구역으로 옮겨 주시면" if zone_key == "other_unit"
        else "차량을 다른 곳으로 옮겨 주시면"
    )
    return res


def nvc_letter_parking(payload: dict, res: dict) -> str:
    """매너 이동 요청 문안 — 비난 없이 사실·영향·요청·부담 낮추기만."""
    plate = res["plate_masked"]
    where = res["location"]
    shot = parse_dt(payload.get("shot_at", "2026-01-01 12:00"))
    when = f"{shot.month}월 {shot.day}일({WEEKDAYS[shot.weekday()]}) {kr_clock(shot)}"

    if res["zone"] == "fire":
        impact = (
            "이 구역은 소방자동차가 화재 시 바로 진입해야 하는 자리로, 지금 주차된 차량 때문에 진입 동선이 끊겨 있습니다."
        )
        ask = "차량을 다른 정식 구획으로 옮겨 주시면"
    elif res["zone"] in ("aisle", "stall_intrusion"):
        impact = "통행로가 좁아져 유모차·이삿짐 운반과 장애인 차량 이동에 불편이 생기고 있습니다."
        ask = "차량을 지정된 구획으로 옮겨 주시면"
    elif res["zone"] == "other_unit":
        impact = "해당 면은 다른 세대에 배정된 지정 주차면입니다."
        ask = "차량을 본인 지정면이나 방문객 구역으로 옮겨 주시면"
    else:
        impact = "통행에 불편이 생기고 있습니다."
        ask = "차량을 다른 곳으로 옮겨 주시면"

    return (
        f"{plate} 차량 운전자님께 — {when} {where}에 주차된 차량을 확인했습니다. "
        f"{impact} 사정이 있으셨을 수 있다고 생각합니다. 다만 {ask} 이웃들이 훨씬 편하게 지나다닐 수 있을 것 같습니다. "
        f"확인 후 이동해 주시면 감사하겠습니다. 바로 답을 주지 않으셔도 괜찮습니다."
    )


def evaluate(payload: dict) -> dict:
    if payload.get("kind") == "parking":
        return evaluate_parking(payload)
    return evaluate_noise(payload)


# ────────────────────────────────────────────────────────────────
# 5. 기준표 노출 (화면이 엔진과 같은 숫자를 쓰도록 단일 출처)
# ────────────────────────────────────────────────────────────────
def standards() -> dict:
    return {
        "engine": {"name": ENGINE_NAME, "version": ENGINE_VERSION},
        "noise": {
            "source": "「공동주택 층간소음의 범위와 기준에 관한 규칙」 제3조 및 별표 (2023. 1. 2. 개정)",
            "rows": [
                {
                    "type": "impact", "type_label": "직접충격", "metric": "1분 등가소음도 Leq",
                    "day": NOISE_STD["impact"]["leq"]["주간"], "night": NOISE_STD["impact"]["leq"]["야간"],
                },
                {
                    "type": "impact", "type_label": "직접충격", "metric": "최고소음도 Lmax (1시간 3회)",
                    "day": NOISE_STD["impact"]["lmax"]["주간"], "night": NOISE_STD["impact"]["lmax"]["야간"],
                },
                {
                    "type": "air", "type_label": "공기전달", "metric": "5분 등가소음도 Leq",
                    "day": NOISE_STD["air"]["leq"]["주간"], "night": NOISE_STD["air"]["leq"]["야간"],
                },
            ],
            "bands": {"day": "06:00–22:00", "night": "22:00–06:00"},
            "grace": {
                "approval_before": GRACE["approval_before"], "effective_from": GRACE["effective_from"],
                "delta_db": GRACE["delta_db"],
            },
        },
        "parking": {
            "fire": {
                "law": "「소방기본법」 제21조의2 제2항 · 제56조 제3항 및 시행령 별표 3",
                "first": FIRE_FINE["first"], "repeat": FIRE_FINE["repeat"], "authority": "관할 소방서",
            }
        },
        "gates": {"confidence_min": GATES["confidence_min"], "citation_min": GATES["citation_min"]},
    }


if __name__ == "__main__":      # 간단 자체 점검
    demo = {
        "kind": "noise",
        "complex": {"name": "새들마을 3단지", "approval_date": "2014-05-20"},
        "unit": {"from": "401", "to": "302"},
        "noise_type": "impact",
        "sound_label": "발소리",
        "confidence": 0.94,
        "events": [
            {"at": "2026-11-22T23:20", "lmax": 58, "leq": 37},
            {"at": "2026-11-22T23:28", "lmax": 57, "leq": 36},
            {"at": "2026-11-22T23:40", "lmax": 58, "leq": 37},
        ],
    }
    out = evaluate(demo)
    print(out["result"], out["severity"]["label"], f"+{out['exceeded_db']} dB", out["gate"])
    print(out["nvc_letter"])
