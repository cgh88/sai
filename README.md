# 사이(Sai) — 공동주택 층간소음·불법·이중주차 갈등 자율조정 AI 에이전트

> **갈등의 사이를, 대화의 사이로.**
> 입주민이 밤 11시 20분에 남기는 신고 4개와 사진 1장을, **인용이 붙은 근거 · 코드가 계산한 판정 · 비폭력(NVC) 조정문**으로 바꿔
> 3분 안에 관리사무소의 처리 기록까지 남깁니다.

| 항목 | 내용 |
| --- | --- |
| 대회 | 라이너 .EXE-THON 2026 (만 40세 이상 AI 에이전트 해커톤) |
| 팀 | Jerad · 조기홍 (개인 참가) |
| 제출물 | 소스코드(이 저장소) · 5분 데모 영상 · 기획서 PDF |
| 기술 | Python FastAPI · 바닐라 ES Modules · Three.js + Polyfork GLB |
| Liner API | **Search Agent API** (`/api/v1/agents/search`, SSE) · **Router API** (`/api/v1/chat/completions`) · Credits balance |

---

## 1. 한 줄 실행

```bash
cd sai-app
pip install -r requirements.txt
uvicorn backend.main:app --port 8000
# 브라우저에서 http://127.0.0.1:8000
```

- **API 키가 없어도 그대로 시연됩니다.** 키가 없으면 `[데모 시드 모드]`로 동작하고, 화면 오른쪽 위 배지로
  `[실시간 Liner API]` / `[데모 시드 모드]`가 구분됩니다. 판정·근거 카드·문서·대시보드 흐름은 두 모드가 동일합니다.
- Liner 실호출을 쓰려면:

```bash
cd sai-app
cp .env.example .env      # LINER_API_KEY=... 채우기
uvicorn backend.main:app --port 8000
```

> `.env` 는 `.gitignore` 에 포함되어 있고, 제출 압축본에도 들어가지 않습니다.
> API 키는 서버 프로세스에서만 읽고 **화면·응답·로그 어디에도 출력하지 않습니다**(테스트로 검증).

### 테스트

```bash
cd sai-app
pytest -q                       # 49 passed (룰 20건 + API · Liner 실시간 경로 목 검증)
python3 backend/rule_engine.py  # 룰 엔진 단독 실행(데모 1건 즉시 판정)
```

---

## 2. 화면 4뷰 (데모 영상 17씬 대응)

상단 탭 또는 `Alt+1~4` 로 전환합니다. 뷰마다 촬영에 필요한 상태가 즉시 재현됩니다.

| 뷰 | 탭 | 대응 씬 | 내용 |
| --- | --- | --- | --- |
| **1. 도입·아키텍처** | ① 도입·아키텍처 | 1–3, 13–17 | 8장 슬라이드: 23:20 도입 → 하루 93건(102,124 카운트업·53.9% 도넛) → 「사이」소개 → 2단 신뢰 아키텍처 → 원가 $0.07/월 $1.3 → 성과(−70%) → 2027 로드맵 → 엔드카드 |
| **2. 입주민 모바일** | ② 입주민 모바일 | 4–7, 8–11 | 430px 폰 프레임. 층간소음 신고(4개 입력) → 근거 카드 3장 스트리밍 → 판정 배지·막대그래프 → NVC 조정문(직접 수정) → 익명 전송 → 관리소 보고서. 불법주차(사진·번호판 마스킹) → 소방법 과태료 → 알림톡 미리보기 |
| **3. 3D 공간 관제** | ③ 3D 공간 관제 | 10 | Three.js 지하주차장 디지털 트윈. 키 `1` 진입로 / `2` 상공 탑 / `3` 위반 분석, `?hud=0` 촬영 모드 |
| **4. 관리사무소 대시보드** | ④ 관리사무소 대시보드 | 12 | 오늘 접수 5건 · 승인 대기 1건, KPI 4개, 민원 목록·상세(근거 3건·초안), 승인/보류, 법령 인용 로그, 주간 브리핑 PDF |

**촬영용 조작**

- 슬라이드: `←` `→`, 하단 점/화살표. 슬라이드가 바뀔 때 카운트업·도넛이 다시 돕니다.
- 모바일: 무대 위 `[씬 4–7 층간소음]` `[씬 8–11 주차]` `[초기화]` 버튼으로 프리셋을 즉시 채웁니다.
  입력 프리셋 칩 `23:20 · 58dB(A) · 발소리`(브리프 지정값)와 `씬 6 대본값(등가 42dB)`도 있습니다.
- 3D: 뷰 진입 시 로드, 다른 뷰로 이동하면 WebGL 을 내려 녹화 중 CPU 를 비웁니다. `[키 1·2·3 포커스]` 후 키를 누르면 카메라 프리셋이 동작합니다.
- 전체 초기화: `R` (데모 데이터 리셋 + 모바일 홈 + 대시보드 갱신)

---

## 3. 아키텍처 — “숫자는 코드가, 문장은 모델이, 최종 결정은 사람이”

```
입주민 앱(430px)
   │  시각·dB·유형·횟수 4개 / 사진 1장
   ▼
① 사실관계 정규화  ── 번호판·동호수 즉시 마스킹(rule_engine.mask_*)
   ▼
② 1단 판정 엔진 (rule_engine.py, 결정론 · LLM 아님)
   │  · 공동주택 층간소음 규칙 별표: 주간 39/야간 34 dB(A) Leq, 57/52 dB(A) Lmax(1시간 3회)
   │  · 경과규정(+2 dB, 2005-06-30 이전 승인 단지) 자동 분기
   │  · 소방기본법 제21조의2·제56조: 과태료 50만 원 / 1년 내 2회 100만 원
   ▼
③ 게이트  ── 인용 0건이면 판정 보류 · 신뢰도 < 0.7 보류 · 위협 표현 차단
   ▼
④ Liner Search Agent API ── 법령·규약 실시간 검색, 인용(`references`)이 본문보다 먼저 도착
   ▼
⑤ Liner Router API ── NVC 조정문(balanced) · 보고서 요약(cost)
   ▼
⑥ 대시보드 · 기록 ── 사람이 승인, 주간 브리핑 PDF
```

### Liner API 사용 지점

| 기능 | 엔드포인트 | 이 서비스에서의 역할 | 코드 |
| --- | --- | --- | --- |
| 근거 검색 | `POST /api/v1/agents/search` (`stream:true`, `lang:ko`, `mode:general`) | 법령·관리규약을 검색해 **인용이 붙은 근거 카드**로. `data-search-references` → `data-search-chunks` → `text-delta*` → `finish` 를 백엔드에서 그대로 중계(SSE→SSE) | `backend/liner_client.py::search_stream`, `backend/main.py::/api/legal/stream` |
| 문장 생성 | `POST /api/v1/chat/completions` (`model: liner-gpt-router`) | NVC 조정문(`routing_strategy=balanced`), 관리소 보고 요약(`cost`) | `backend/liner_client.py::chat`, `/api/case/{id}/letter`, `/api/case/{id}/report` |
| 크레딧 확인 | `GET /api/v1/credits/balance` | `/api/health` 에서 잔액·지연 표시(키가 있을 때만). 키는 응답에 담지 않음 | `/api/health` |

- 라우터 모델·전략은 `.env` 로 바꿀 수 있습니다(`LINER_CHAT_MODEL`, `LINER_ROUTING_LETTER`, `LINER_ROUTING_REPORT`).
- 실호출이 401/402/네트워크로 실패하면 **시드로 폴백**하고 SSE 첫 이벤트에 `fallback: true` 를 실어 화면 배지를 `폴백 · 시드`로 바꿉니다(데모가 멈추지 않게).
- `backend/tests/mock_liner_server.py` 는 위 3개 엔드포인트를 **실제 응답 규격 그대로** 흉내 내는 목 서버입니다. `pytest` 가 이 목으로 [실시간 Liner API] 경로(SSE 순서·중계·Router 라우팅·balane)를 검증합니다.

---

## 4. 데모 시드 모드 (키 없이 5분 시연)

| 프리셋 | 값 | 결과 |
| --- | --- | --- |
| **케이스 3** (씬 4–7) | 23:20 · 최고 58 dB(A) · 등가 37 dB(A) · 1시간 3회 · 발소리(직접충격) | 야간 기준(Lmax 52 / Leq 34) **초과 +6 dB** → `기준 초과 · 주의` · 자동 처리 · 근거 3건 |
| **케이스 7** (씬 8–11) | 소방자동차 전용구역 · 19:12 · `12가****` | **과태료 50만 원**(1년 내 2회부터 100만 원) · 부과 권한 관할 소방서 · 즉시 이동 요청 |
| 씬 6 대본값 | 23:20 · 등가 42 dB(A) · 최고 49 dB(A) | 등가소음도 초과(+8 dB) · 최고소음도 이내 |

시드 응답은 Liner Search Agent 응답 포맷(`references`/`referenceChunks`/`text-delta`)을 그대로 재생하며,
대시보드의 5건·KPI·인용 로그도 **같은 룰 엔진**으로 계산합니다(화면 숫자와 엔진 숫자가 갈라지지 않음).

---

## 5. 폴더 구조

```
sai-app/
├─ backend/
│  ├─ main.py              FastAPI 앱 · 정적 서빙 · API · SSE 중계
│  ├─ rule_engine.py       1단 결정론 룰 엔진 + 개인정보 마스킹 + 기준표(단일 출처)
│  ├─ liner_client.py      Liner Search(SSE) · Chat(Router) · Credits
│  ├─ prompts.py           검색 질의 · NVC 프롬프트(비난 금지·요청 1개·신원 비노출)
│  ├─ documents.py         중재 보고서 필드 · 주간 브리핑 · NVC 자체 점검
│  ├─ seed_data.py         가상 단지·세대·차량 시드(개인정보 0건)
│  ├─ store.py             오늘 5건 · 인용 로그 · 승인 상태(메모리)
│  ├─ settings.py          .env 로더(키는 공개 설정에 포함하지 않음)
│  └─ tests/               test_rule_engine.py(20건+α) · test_api.py · mock_liner_server.py
├─ frontend/
│  ├─ index.html           4뷰 셸
│  ├─ css/app.css
│  ├─ js/app.js            뷰 전환 · 배지 · 키보드 · 3D 로드 제어
│  ├─ js/slides.js         슬라이드 8장 · 카운트업/도넛
│  ├─ js/mobile.js         입주민 앱(신고→근거→판정→문서→발송)
│  ├─ js/dashboard.js      관리소 관제(목록·상세·승인·로그)
│  ├─ print.html           중재 보고서·주간 브리핑 A4 인쇄(PDF로 저장)
│  ├─ 3d_viewer.html       Three.js 지하주차장 뷰어(씬 10)
│  ├─ vendor/              three.js 0.180 + OrbitControls + GLTFLoader (오프라인 동작)
│  └─ assets/              Polyfork GLB 2종 · 가상 주차 사진 3장(합성)
├─ screenshots/            검증 스크린샷 17장
├─ .env.example · .gitignore · requirements.txt
└─ README.md
```

---

## 6. 검증 결과 (2026-11-22, 로컬 실측)

- **룰 엔진** `pytest backend/tests/test_rule_engine.py` → **32 passed** (야간/주간 경계 06:00·05:59·22:00·21:59, 경과규정, Lmax 3회, Leq, 공기전달, 범위 밖, 신뢰도·위협·인용 게이트, 주차 5건, 마스킹)
- **API·Liner 경로** `pytest backend/tests/test_api.py` → **17 passed** (health·config·noise/parking·SSE 순서·letter·report·dashboard·approve·404·정적파일 + 목 서버로 실시간 SSE 중계/ Router 라우팅/ 크레딧/ 폴백)
- **브라우저 렌더** 1920×1080 헤드리스 Chromium으로 4뷰 전환·시연 플로우 실행 → 콘솔 오류 0 · 페이지 오류 0
- 스크린샷: `screenshots/01_slide_intro.png` … `17_report_print.png`

---

## 7. 경계와 개인정보

- 「사이」는 **판단 보조 도구**입니다. 법적 판결·과태료 부과 대행·상시 녹음/감시·당사자 신원 공개는 범위 밖이며,
  최종 판단과 처분은 관리주체·지자체·법원의 권한입니다. (화면·보고서 하단 고정 문구)
- 차량번호(`12가3456 → 12가****`), 신고 세대(`105-401 → 105동 4**호`), 전화번호는 **접수 즉시 마스킹**되어
  응답·대시보드·로그·문서 어디에도 원본이 남지 않습니다(테스트로 검증).
- 모든 단지·세대·차량은 가상값이며, 화면 하단에
  `본 화면의 단지·세대·차량 정보는 모두 가상 데이터입니다` 를 고정 표기합니다.
- 앱 dB 값은 ±3 dB 오차를 감안해 `기준 초과 / 초과 의심`으로 나누고, 정밀 측정은 이웃사이센터 현장진단으로 안내합니다.

---

## 8. 참고

- `screenshots/` 는 검증용 캡처입니다. 데모 영상은 이 앱을 띄워 놓고 OBS **창 캡처**(모바일 430px 창 / 3D 창 / 대시보드 창 / 슬라이드 창)로 촬영하면
  `documents/라이너_해커톤_5분_데모_영상_시나리오.md` 의 17씬과 1:1로 맞습니다.
- PDF 버튼은 브라우저 인쇄(A4) 로 동작합니다 — Chrome 인쇄 대화상자에서 **PDF로 저장**.
- 3D 뷰어는 `?hud=0`(HUD 숨김), `?preset=top`, `?violation=0` 파라미터를 그대로 지원합니다.
