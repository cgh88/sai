# -*- coding: utf-8 -*-
"""데모 시드 데이터 — 가상 단지·세대·차량만 사용한다(개인정보 0건, 참가규정 제5조).

여기 있는 값은 5분 데모 시나리오의 프리셋과 대시보드 5건을 구성한다.
  · 케이스 3 : 층간소음 23:20 · 최고 58 dB(A) · 발소리  (씬 4~7)
  · 케이스 7 : 소방자동차 전용구역 불법주차              (씬 8~11)
모든 판정은 rule_engine 이 계산한다(시드도 예외 없음) — 화면 숫자와 엔진 숫자가 갈라지지 않는다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

COMPLEX = {"name": "새들마을 3단지", "approval_date": "2014-05-20", "households": 300}

DISCLAIMER = "본 화면의 단지·세대·차량 정보는 모두 가상 데이터입니다."


def _today() -> date:
    return date.today()


def _at(hhmm: str, day_offset: int = 0) -> str:
    base = _today() + timedelta(days=day_offset)
    return f"{base.isoformat()}T{hhmm}"


# ────────────────────────────────────────────────────────────────
# 1. 데모 프리셋 (씬 4~7 / 씬 8~11)
# ────────────────────────────────────────────────────────────────
def noise_preset(case_id: str = "C-003", variant: str = "case3") -> dict:
    """variant='case3'  → 23:20 · Lmax 58 dB(A) · Leq 37 dB(A) · 3회  (브리프 지정 프리셋)
       variant='scene6' → 23:20 · Lmax 49 dB(A) · Leq 42 dB(A) · 등가소음도 초과(씬 6 대본값)
    """
    if variant == "scene6":
        events = [
            {"at": _at("23:20"), "lmax": 49, "leq": 42},
            {"at": _at("23:31"), "lmax": 47, "leq": 40},
        ]
    else:
        events = [
            {"at": _at("23:20"), "lmax": 58, "leq": 37},
            {"at": _at("23:28"), "lmax": 57, "leq": 36},
            {"at": _at("23:40"), "lmax": 58, "leq": 37},
        ]
    return {
        "kind": "noise",
        "case_id": case_id,
        "complex": COMPLEX,
        "unit": {"from": "401", "to": "302"},
        "noise_type": "impact",
        "sound_label": "발소리",
        "duration_min": 20,
        "confidence": 0.94,
        "message": "",
        "household_context": "다음 날 학교에 가야 하는 아이가 있어 밤 11시 이후에는 조용한 환경이 꼭 필요합니다.",
        "request": "슬리퍼 착용과 아이의 뛰는 놀이를 잠시 멈춰 주시면",
        "events": events,
    }


def parking_preset(case_id: str = "C-007", variant: str = "case7") -> dict:
    """variant='case7' → 소방자동차 전용구역(과태료 50만 원) / 'aisle' → 통로 이중주차."""
    if variant == "aisle":
        return {
            "kind": "parking",
            "case_id": case_id,
            "complex": COMPLEX,
            "zone": "aisle",
            "location": "지하 2층 진입로 통로(경사로 하단)",
            "shot_at": _at("21:40"),
            "plate_ocr": "56다1234",
            "prior_violations_12m": 0,
            "confidence": 0.88,
            "shots": 1,
            "preset_photo": "aisle",
        }
    return {
        "kind": "parking",
        "case_id": case_id,
        "complex": COMPLEX,
        "zone": "fire",
        "location": "지하 2층 B-27 소방자동차 전용구역",
        "shot_at": _at("19:12"),
        "plate_ocr": "12가3456",
        "prior_violations_12m": 0,
        "confidence": 0.91,
        "shots": 2,
        "preset_photo": "fire",
    }


# ────────────────────────────────────────────────────────────────
# 2. 관리사무소 대시보드 — 오늘 접수 5건
# ────────────────────────────────────────────────────────────────
def case_definitions() -> list[dict]:
    """id · payload · 접수 상태 · 처리 시간(분) · 문서 생성 시간(분) · 담당."""
    low_conf = noise_preset("C-008", "scene6")
    low_conf["unit"] = {"from": "501", "to": "402"}
    low_conf["confidence"] = 0.62
    low_conf["household_context"] = "아이가 잠드는 시간이 들쭉날쭉해서 그 시간대 소리가 유난히 크게 들립니다."

    aisle = parking_preset("C-005", "aisle")
    other = parking_preset("C-011", "case7")
    other.update(
        zone="other_unit",
        location="지하 2층 302호 지정면",
        shot_at=_at("20:15"),
        plate_ocr="78라5678",
        confidence=0.86,
        shots=1,
        preset_photo="other_unit",
    )

    return [
        {
            "id": "C-003",
            "kind": "noise",
            "payload": noise_preset("C-003", "case3"),
            "received_at": _at("23:20"),
            "status": "승인 대기",
            "urgency": "주의",
            "processing_min": 24,
            "letter_min": 3,
            "assignee": "관리소 주무",
            "note": "조정문 초안 완료 · 관리소 승인 대기",
        },
        {
            "id": "C-007",
            "kind": "parking",
            "payload": parking_preset("C-007", "case7"),
            "received_at": _at("19:12"),
            "status": "이동 요청 발송",
            "urgency": "긴급",
            "processing_min": 29,
            "letter_min": 3,
            "assignee": "관리소 주무",
            "note": "30분 내 미이동 시 관리소 보고 · 소방서 신고 안내",
        },
        {
            "id": "C-005",
            "kind": "parking",
            "payload": aisle,
            "received_at": _at("21:40"),
            "status": "처리 완료",
            "urgency": "보통",
            "processing_min": 18,
            "letter_min": 2,
            "assignee": "관리소 주무",
            "note": "차주 이동 완료 · 이력 기록",
        },
        {
            "id": "C-008",
            "kind": "noise",
            "payload": low_conf,
            "received_at": _at("22:35"),
            "status": "검토 대기",
            "urgency": "보통",
            "processing_min": 25,
            "letter_min": 4,
            "assignee": "관리과장",
            "note": "신뢰도 0.62 — 자동 발송 보류, 사람 확인 필요",
        },
        {
            "id": "C-011",
            "kind": "parking",
            "payload": other,
            "received_at": _at("20:15"),
            "status": "처리 완료",
            "urgency": "낮음",
            "processing_min": 39,
            "letter_min": 3,
            "assignee": "관리소 주무",
            "note": "타 세대 지정면 — 이동 요청 후 완료",
        },
    ]


KPI_BENCHMARK = [
    {"key": "letter", "label": "문서 생성", "from": "90분", "to": "3분", "unit": "분",
     "from_value": 90, "to_value": 3, "note": "조정문·보고서·발송문"},
    {"key": "total", "label": "총 처리(검토·승인 포함)", "from": "90분", "to": "27분", "unit": "분",
     "from_value": 90, "to_value": 27, "note": "민원 1건 기준"},
    {"key": "evidence", "label": "증빙 일지 작성률", "from": "30%", "to": "95%", "unit": "%",
     "from_value": 30, "to_value": 95, "note": "기록 없는 민원 소멸"},
    {"key": "repeat", "label": "2주 내 재민원", "from": "25%", "to": "12%", "unit": "%",
     "from_value": 25, "to_value": 12, "note": "같은 세대 반복 신고"},
]


# ────────────────────────────────────────────────────────────────
# 3. 법령·규약 시드 응답 (Liner Search Agent 응답 포맷 그대로)
# ────────────────────────────────────────────────────────────────
def _ref(title, url, hostname, description, date_text, search_query):
    return {
        "title": title,
        "url": url,
        "hostname": hostname,
        "faviconUrl": None,
        "description": description,
        "date": date_text,
        "searchQuery": search_query,
    }


NOISE_QUERY = (
    "공동주택 층간소음 야간(22:00~06:00) 직접충격 소음 1분 등가소음도 34dB 최고소음도 52dB 기준, "
    "공동주택관리법 제20조 관리주체 조치, 공동주택 관리규약 생활소음 조항"
)

PARKING_QUERY = (
    "소방자동차 전용구역 주차 금지 소방기본법 제21조의2 제2항, 과태료 1회 50만원 1년 내 2회 100만원 "
    "소방기본법 제56조 제3항 시행령 별표 3, 공동주택 관리규약 주차질서"
)


def evidence_seed(kind: str, case: dict | None = None) -> dict:
    """Search Agent 의 data-search-references / data-search-chunks / text-delta 에 대응하는 시드."""
    if kind == "parking":
        refs = [
            _ref(
                "소방기본법 제21조의2 (소방자동차 전용구역의 설치·관리)",
                "https://www.law.go.kr/법령/소방기본법",
                "law.go.kr",
                "제21조의2 제2항 — 소방자동차 전용구역에 차를 주차하거나 전용구역 진입을 가로막는 행위를 하여서는 아니 된다.",
                "2024-01-01",
                PARKING_QUERY,
            ),
            _ref(
                "소방기본법 제56조 제3항 및 시행령 별표 3 (과태료)",
                "https://www.law.go.kr/법령/소방기본법시행령",
                "law.go.kr",
                "전용구역 주차 위반 과태료 — 1차 50만 원, 1년 내 2회 이상 100만 원.",
                "2024-01-01",
                PARKING_QUERY,
            ),
            _ref(
                "새들마을 3단지 관리규약 제12조(주차질서) — 단지 규약 인덱스",
                "https://sai.local/rules/saedeul-3#제12조",
                "sai.local",
                "제12조 — 소방자동차 전용구역·통로·타 세대 지정면 주차 금지, 관리주체는 이동 요청과 기록 의무를 진다. (가상 규약, pgvector 인덱스 검색)",
                "2025-03-01",
                PARKING_QUERY,
            ),
        ]
        answer = (
            "야간이든 주간이든 소방자동차 전용구역에는 주차할 수 없습니다 [1]. "
            "위반 시 과태료는 1회 50만 원, 1년 내 2회 이상이면 100만 원이며 부과 권한은 관할 소방서에 있습니다 [2]. "
            "이 단지 관리규약 제12조는 같은 금지를 정하고, 관리주체가 이동 요청과 기록을 남기도록 합니다 [3]. "
            "즉시 이동이 필요한 사안인지, 과태료 대상인지는 위치와 이력으로 판정 엔진이 대조합니다."
        )
        chunks = [
            {"num": 1, "content": "제21조의2 제2항 소방자동차 전용구역에 차를 주차하거나 전용구역 진입을 가로막는 행위를 하여서는 아니 된다.",
             "sourceTitle": "소방기본법 제21조의2", "sourceUrl": "https://www.law.go.kr/법령/소방기본법"},
            {"num": 2, "content": "별표 3 — 소방자동차 전용구역 주차 위반 과태료 1차 50만 원, 1년 내 2회 이상 100만 원.",
             "sourceTitle": "소방기본법 시행령 별표 3", "sourceUrl": "https://www.law.go.kr/법령/소방기본법시행령"},
            {"num": 3, "content": "제12조 — 전용구역·통로·타 세대 지정면 주차 금지, 관리주체의 이동 요청·기록 의무.",
             "sourceTitle": "새들마을 3단지 관리규약 제12조", "sourceUrl": "https://sai.local/rules/saedeul-3#제12조"},
        ]
        return {"query": PARKING_QUERY, "references": refs, "chunks": chunks, "answer": answer}

    refs = [
        _ref(
            "공동주택 층간소음의 범위와 기준에 관한 규칙 (제3조 및 별표)",
            "https://www.law.go.kr/법령/공동주택층간소음의범위와기준에관한규칙",
            "law.go.kr",
            "별표 — 직접충격 소음 1분 등가소음도 주간 39 dB(A)·야간 34 dB(A), 최고소음도 주간 57 dB(A)·야간 52 dB(A), 최고소음도는 1시간 내 3회 이상 초과 시 기준 초과.",
            "2023-01-02",
            NOISE_QUERY,
        ),
        _ref(
            "공동주택관리법 제20조 (층간소음 기준 초과 시 관리주체의 조치)",
            "https://www.law.go.kr/법령/공동주택관리법",
            "law.go.kr",
            "제20조 — 층간소음 기준을 초과하면 관리주체는 해당 세대에 알리고, 필요한 조치와 기록을 하여야 한다.",
            "2024-07-01",
            NOISE_QUERY,
        ),
        _ref(
            "새들마을 3단지 관리규약 제18조(층간소음) — 단지 규약 인덱스",
            "https://sai.local/rules/saedeul-3#제18조",
            "sai.local",
            "제18조 — 야간 22시부터 06시까지 생활소음 금지, 분쟁 시 관리사무소가 중재에 나선다. (가상 규약, pgvector 인덱스 검색)",
            "2025-03-01",
            NOISE_QUERY,
        ),
    ]
    answer = (
        "야간(22:00~06:00) 직접충격 소음의 1분 등가소음도 기준은 34 dB(A)입니다 [1]. "
        "최고소음도 기준은 52 dB(A)이고, 1시간 내 3회 이상 넘으면 기준 초과로 봅니다 [1]. "
        "기준을 넘으면 관리주체는 「공동주택관리법」 제20조에 따라 해당 세대에 알리고 조치·기록을 남겨야 합니다 [2]. "
        "이 단지 관리규약 제18조는 22시 이후 생활소음을 금지하고 중재 절차를 정하고 있습니다 [3]. "
        "신고된 측정값을 이 기준에 대조하는 계산은 판정 엔진이 수행하고, 근거 인용이 2건 미만이면 판정을 보류합니다."
    )
    chunks = [
        {"num": 1, "content": "별표 — 직접충격 소음 1분 등가소음도 야간 34 dB(A), 최고소음도 야간 52 dB(A), 1시간 내 3회 이상 초과 시 기준 초과.",
         "sourceTitle": "공동주택 층간소음의 범위와 기준에 관한 규칙", "sourceUrl": "https://www.law.go.kr/법령/공동주택층간소음의범위와기준에관한규칙"},
        {"num": 2, "content": "제20조 — 층간소음 기준 초과 시 관리주체의 통지·조치·기록 의무.",
         "sourceTitle": "공동주택관리법 제20조", "sourceUrl": "https://www.law.go.kr/법령/공동주택관리법"},
        {"num": 3, "content": "제18조 — 야간 22시~06시 생활소음 금지, 관리사무소 중재.",
         "sourceTitle": "새들마을 3단지 관리규약 제18조", "sourceUrl": "https://sai.local/rules/saedeul-3#제18조"},
    ]
    return {"query": NOISE_QUERY, "references": refs, "chunks": chunks, "answer": answer}


# ────────────────────────────────────────────────────────────────
# 4. 대시보드 법령 인용 로그(오늘) — 검색이 일어나면 store 가 이어서 쌓는다
# ────────────────────────────────────────────────────────────────
def citation_log_seed() -> list[dict]:
    def stamp(hhmm: str) -> str:
        return f"{_today().isoformat()} {hhmm}"

    return [
        {"at": stamp("19:13"), "case_id": "C-007", "query_kind": "parking", "citations": 3,
         "docs": ["소방기본법 제21조의2", "소방기본법 제56조 제3항", "관리규약 제12조"], "gate": "자동 처리"},
        {"at": stamp("19:41"), "case_id": "C-011", "query_kind": "parking", "citations": 2,
         "docs": ["관리규약 제12조", "공동주택관리법 제18조"], "gate": "자동 처리"},
        {"at": stamp("20:16"), "case_id": "C-011", "query_kind": "parking", "citations": 2,
         "docs": ["관리규약 제12조", "공동주택관리법 제18조"], "gate": "자동 처리"},
        {"at": stamp("21:41"), "case_id": "C-005", "query_kind": "parking", "citations": 2,
         "docs": ["관리규약 제12조", "공동주택관리법 제18조"], "gate": "자동 처리"},
        {"at": stamp("22:36"), "case_id": "C-008", "query_kind": "noise", "citations": 3,
         "docs": ["층간소음 규칙 별표", "공동주택관리법 제20조", "관리규약 제18조"], "gate": "보류"},
        {"at": stamp("23:21"), "case_id": "C-003", "query_kind": "noise", "citations": 3,
         "docs": ["층간소음 규칙 별표", "공동주택관리법 제20조", "관리규약 제18조"], "gate": "자동 처리"},
    ]


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
