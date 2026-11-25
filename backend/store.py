# -*- coding: utf-8 -*-
"""메모리 스토어 — 오늘 접수 5건 · 인용 로그 · 승인 상태. (데모용, 재시작하면 시드로 돌아간다)"""

from __future__ import annotations

import threading
from datetime import datetime

import documents
import rule_engine
import seed_data


class Store:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.cases: dict[str, dict] = {}
        self.citation_log: list[dict] = []
        self.last_evidence: dict[str, str] = {}
        self.counter = 12
        self.reset()

    # ── 시드 ──────────────────────────────────────────────────
    def reset(self) -> None:
        with self._lock:
            self.cases = {}
            self.citation_log = sorted(seed_data.citation_log_seed(), key=lambda r: r["at"], reverse=True)
            self.last_evidence = {}
            self.counter = 12
            for definition in seed_data.case_definitions():
                case = {
                    **{k: v for k, v in definition.items() if k != "payload"},
                    "payload": definition["payload"],
                    "result": rule_engine.evaluate(definition["payload"]),
                }
                self._finalize(case, letter_source="seed")
                self.cases[case["id"]] = case

    def _finalize(self, case: dict, letter_source: str = "seed", summary: str = "") -> None:
        result = case["result"]
        letter = case.get("letter") or result.get("nvc_letter") or ""
        case["letter"] = letter
        case["letter_source"] = letter_source
        case["checks"] = documents.nvc_checks(letter)
        case["report"] = documents.report_fields(result, case["payload"])
        case["summary"] = summary
        case["citations_used"] = result.get("citations", [])
        case["updated_at"] = datetime.now().isoformat(timespec="seconds")

    # ── 접근 ──────────────────────────────────────────────────
    def get(self, case_id: str) -> dict | None:
        return self.cases.get(case_id)

    def ordered(self) -> list[dict]:
        return sorted(
            self.cases.values(),
            key=lambda c: (documents.STATUS_ORDER.get(c["urgency"], 9), c["received_at"]),
        )

    def next_id(self, kind: str) -> str:
        with self._lock:
            self.counter += 1
            return f"C-{self.counter:03d}"

    def upsert(self, payload: dict, *, letter: str = "", letter_source: str = "seed",
               summary: str = "", received_at: str | None = None) -> dict:
        """신고 1건 반영 — 데모에서는 프리셋 case_id(C-003·C-007)를 갱신한다."""
        result = rule_engine.evaluate(payload)
        case_id = payload.get("case_id") or self.next_id(payload.get("kind", "noise"))
        payload = {**payload, "case_id": case_id}
        existing = self.cases.get(case_id)

        if result["kind"] == "noise":
            urgency = "주의" if result["result"] == "기준 초과" else "보통"
            note = "조정문 초안 완료 · 관리소 승인 대기" if result["gate"] == "자동 처리" else result["gate_reason"]
        else:
            urgency = result["urgency"]
            note = "이동 요청 알림톡 발송 대기" if result["gate"] == "자동 처리" else result["gate_reason"]

        status = "승인 대기" if result["gate"] == "자동 처리" else "검토 대기"
        case = {
            "id": case_id,
            "kind": result["kind"],
            "payload": payload,
            "received_at": received_at or (existing or {}).get("received_at") or datetime.now().isoformat(timespec="minutes"),
            "status": status,
            "urgency": urgency,
            "processing_min": (existing or {}).get("processing_min", 0) or self._estimate_minutes(result),
            "letter_min": (existing or {}).get("letter_min", 3),
            "assignee": (existing or {}).get("assignee", "관리소 주무"),
            "note": note,
            "result": result,
            "letter": letter or result.get("nvc_letter") or "",
        }
        self._finalize(case, letter_source=letter_source, summary=summary)
        with self._lock:
            self.cases[case_id] = case
        return case

    @staticmethod
    def _estimate_minutes(result: dict) -> int:
        base = 26 if result["kind"] == "noise" else 24
        return base if result["gate"] == "자동 처리" else base + 6

    # ── 상태 변경 · 로그 ──────────────────────────────────────
    def approve(self, case_id: str, action: str = "approve") -> dict | None:
        case = self.cases.get(case_id)
        if not case:
            return None
        with self._lock:
            if action == "hold":
                case["status"] = "검토 대기"
                case["note"] = "관리소 보류 — 사람이 추가 확인"
            else:
                case["status"] = "발송 완료"
                case["note"] = "관리소 승인 · 익명 발송 완료 · 기록 저장"
                case["processing_min"] = max(9, case["processing_min"] - 12)
            case["updated_at"] = datetime.now().isoformat(timespec="seconds")
            self.log_citation(
                case_id=case_id,
                query_kind=case["kind"],
                citations=len(case["result"].get("citations", [])),
                docs=[f"{c['doc']} {c['article']}" for c in case["result"].get("citations", [])],
                gate=case["result"]["gate"],
                event="승인" if action != "hold" else "보류",
            )
        return case

    def log_citation(self, *, case_id: str, query_kind: str, citations: int, docs: list[str],
                     gate: str, event: str = "검색") -> dict:
        entry = {
            "at": datetime.now().isoformat(timespec="seconds"),
            "case_id": case_id,
            "query_kind": query_kind,
            "citations": citations,
            "docs": docs,
            "gate": gate,
            "event": event,
        }
        with self._lock:
            self.citation_log.insert(0, entry)
            self.citation_log = self.citation_log[:200]
        return entry

    # ── 대시보드 ──────────────────────────────────────────────
    def dashboard(self) -> dict:
        cases = self.ordered()
        total = len(cases)
        avg_total = round(sum(c["processing_min"] for c in cases) / total, 1) if total else 0
        avg_letter = round(sum(c["letter_min"] for c in cases) / total, 1) if total else 0
        pending = sum(1 for c in cases if c["status"] == "승인 대기")

        kpis = [
            {"key": "letter", "label": "문서 생성", "from_value": 90, "to_value": avg_letter,
             "from": "90분", "to": f"{avg_letter:.0f}분", "unit": "분", "note": "조정문·보고서·발송문", "basis": "오늘 실측"},
            {"key": "total", "label": "총 처리(검토·승인 포함)", "from_value": 90, "to_value": avg_total,
             "from": "90분", "to": f"{avg_total:.0f}분", "unit": "분",
             "delta_pct": round((avg_total - 90) / 90 * 100), "note": "민원 1건 기준", "basis": "오늘 실측"},
            {"key": "evidence", "label": "증빙 일지 작성률", "from_value": 30, "to_value": 95,
             "from": "30%", "to": "95%", "unit": "%", "note": "기록 없는 민원 소멸", "basis": "파일럿 벤치마크"},
            {"key": "repeat", "label": "2주 내 재민원", "from_value": 25, "to_value": 12,
             "from": "25%", "to": "12%", "unit": "%", "note": "같은 세대 반복 신고", "basis": "파일럿 벤치마크"},
        ]

        rows = []
        for case in cases:
            result = case["result"]
            if case["kind"] == "noise":
                target = rule_engine.mask_unit(case["payload"].get("unit", {}).get("from", ""))
                kind_label = f"층간소음 · {result.get('noise_label', '')}"
            else:
                target = result.get("plate_masked", "")
                kind_label = f"주차 · {result.get('zone_label', '')}"
            rows.append({
                "id": case["id"],
                "kind": case["kind"],
                "kind_label": kind_label,
                "target": target,
                "received_at": case["received_at"].replace("T", " ")[5:],
                "urgency": case["urgency"],
                "status": case["status"],
                "gate": result["gate"],
                "confidence": result["confidence"],
                "citations": len(result.get("citations", [])),
                "processing_min": case["processing_min"],
                "headline": (f"{result['result']} · +{result['exceeded_db']:.0f} dB" if result["kind"] == "noise"
                             else f"{result['result']} · {result.get('fine_note', '')[:24]}"),
                "note": case["note"],
            })

        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "counts": {"today": total, "pending": pending},
            "kpis": kpis,
            "cases": rows,
            "briefing": documents.briefing_rows(cases),
            "citation_log": self.citation_log[:40],
            "standards": rule_engine.standards(),
            "disclaimer": seed_data.DISCLAIMER,
        }


STORE = Store()
