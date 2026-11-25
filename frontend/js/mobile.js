// 뷰 2 — 입주민 모바일 앱 (430px). 신고 → 근거 → 판정 → 조정문·보고서
import { api, state, esc, withCitations, stream, toast, fmt } from "./api.js";

const UI = { body: null, toast: null, clock: null };
let es = null;
let rafTimer = null;

const SOUND_TYPES = [
  { id: "발소리", label: "발소리·쿵쿵", type: "impact" },
  { id: "가구 끄는 소리", label: "가구 끄는 소리", type: "impact" },
  { id: "망치질", label: "망치질", type: "impact" },
  { id: "아이 뛰는 소리", label: "아이 뛰는 소리", type: "impact" },
  { id: "대화·음악", label: "대화·음악", type: "air" },
  { id: "사람 목소리", label: "그 외(범위 밖)", type: "out_of_scope" },
];

const PHOTOS = {
  fire: ["/assets/parking_fire.jpg", "/assets/parking_plate.jpg"],
  aisle: ["/assets/parking_aisle.jpg"],
  other_unit: ["/assets/parking_fire.jpg"],
};

const ZONE_META = {
  fire: { zone: "fire", label: "소방자동차 전용구역", location: "지하 2층 B-27 소방자동차 전용구역", plate: "12가3456", prior: 0, shots: 2 },
  aisle: { zone: "aisle", label: "통로·진입로 이중주차", location: "지하 2층 진입로 통로(경사로 하단)", plate: "56다1234", prior: 0, shots: 1 },
  other_unit: { zone: "other_unit", label: "타 세대 지정면 주차", location: "지하 2층 302호 지정면", plate: "78라5678", prior: 0, shots: 1 },
};

const F = {
  noise: { at: "23:20", leq: 37, lmax: 58, repeat: 3, duration: 20, sound: "발소리", type: "impact", ctx: true },
  parking: { preset: "fire", uploaded: null },
};

const R = { noise: null, parking: null };   // 마지막 분석 결과
let current = "home";
let timerStart = 0;

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

/* ────────────────────────────────────────────────────────────
   화면 전환 · 공통
   ──────────────────────────────────────────────────────────── */
function show(html, screen) {
  current = screen;
  UI.body.innerHTML = html;
  UI.body.scrollTop = 0;
}

function appBar(title, { back = true, timer = false } = {}) {
  return `<div class="app-bar">
    ${back ? '<button class="back" data-back="1" aria-label="뒤로">←</button>' : ""}
    <div class="ttl">${esc(title)}</div>
    ${timer ? '<span class="timer" id="timer">00:00:00</span>' : ""}
  </div>`;
}

function bindBack() {
  $$("[data-back]").forEach((b) => b.addEventListener("click", () => renderHome()));
}

function setClock(hhmm) {
  if (UI.clock) UI.clock.textContent = hhmm || "23:20";
}

function startTimer() {
  stopTimer();
  timerStart = Date.now();
  const tick = () => {
    const t = Math.floor((Date.now() - timerStart) / 1000);
    const node = $("#timer");
    if (node) {
      const hh = String(Math.floor(t / 3600)).padStart(2, "0");
      const mm = String(Math.floor((t % 3600) / 60)).padStart(2, "0");
      const ss = String(t % 60).padStart(2, "0");
      node.textContent = `${hh}:${mm}:${ss}`;
    }
  };
  tick();
  rafTimer = setInterval(tick, 1000);
}
function stopTimer() { if (rafTimer) { clearInterval(rafTimer); rafTimer = null; } }

/* ────────────────────────────────────────────────────────────
   홈
   ──────────────────────────────────────────────────────────── */
export function renderHome() {
  stopTimer();
  if (es) { es.close(); es = null; }
  setClock(null);
  show(`
    <div class="hello">
      <div class="sm">새들마을 3단지 · 105동 401호</div>
      <div class="lg">무엇을 <b>도와드릴까요?</b></div>
    </div>
    <div class="pick">
      <button class="pick-card" data-go="noise" type="button">
        <div class="ico blue">🔊</div>
        <div class="tx"><div class="t">층간소음 신고</div><div class="s">유형·시각·소음도 4개만 입력</div></div>
        <div class="go">›</div>
      </button>
      <button class="pick-card" data-go="parking" type="button">
        <div class="ico red">🅿️</div>
        <div class="tx"><div class="t">불법·이중주차 신고</div><div class="s">사진 1장 · 번호판 자동 마스킹</div></div>
        <div class="go">›</div>
      </button>
    </div>
    <div class="mini-list">
      <div class="h">최근 신고</div>
      <div class="mini-row"><span class="t">층간소음 · 발소리</span><span style="color:#98a2b3">어제 23:20</span><span class="st ok">처리 완료</span></div>
      <div class="mini-row"><span class="t">주차 · 통로 이중주차</span><span style="color:#98a2b3">11/19 21:40</span><span class="st ok">처리 완료</span></div>
    </div>`);
  $$("[data-go]").forEach((b) => b.addEventListener("click", () => {
    state.mode === "seed" ? null : null;
    if (b.dataset.go === "noise") renderNoiseForm(); else renderParkingForm();
  }));
}

/* ────────────────────────────────────────────────────────────
   층간소음 — 입력
   ──────────────────────────────────────────────────────────── */
export function renderNoiseForm(preset) {
  if (preset === "scene6") {
    Object.assign(F.noise, { at: "23:20", leq: 42, lmax: 49, repeat: 2, duration: 20, sound: "발소리", type: "impact" });
  } else if (preset === "case3") {
    Object.assign(F.noise, { at: "23:20", leq: 37, lmax: 58, repeat: 3, duration: 20, sound: "발소리", type: "impact" });
  }
  setClock(F.noise.at);
  show(`${appBar("층간소음 신고")}
    <div class="preset-row">
      <button class="chip preset" data-preset="case3" type="button">23:20 · 58dB(A) · 발소리</button>
      <button class="chip preset" data-preset="scene6" type="button">씬 6 대본값 (등가 42dB)</button>
    </div>

    <div class="field">
      <div class="lb">소리 유형</div>
      <div class="preset-row" style="margin:8px 0 0">
        ${SOUND_TYPES.map((s) => `<button class="chip ${s.id === F.noise.sound ? "on" : ""}" data-sound="${esc(s.id)}" data-type="${s.type}" type="button">${esc(s.label)}</button>`).join("")}
      </div>
    </div>

    <div class="field">
      <div class="lb">측정 시각</div>
      <div class="ctrl"><input class="time-text" id="f-at" type="text" inputmode="numeric" maxlength="5" value="${F.noise.at}" aria-label="측정 시각 24시각"><span class="clock-ico">◷</span></div>
    </div>

    <div class="field two">
      <div>
        <div class="lb">등가소음도 Leq</div>
        <div class="ctrl"><input type="number" id="f-leq" value="${F.noise.leq}" min="20" max="120" step="1"><span class="unit">dB(A)</span></div>
        <div class="hint">1분 평균</div>
      </div>
      <div>
        <div class="lb">최고소음도 Lmax</div>
        <div class="ctrl"><input type="number" id="f-lmax" value="${F.noise.lmax}" min="20" max="120" step="1"><span class="unit">dB(A)</span></div>
        <div class="hint">가장 큰 순간</div>
      </div>
    </div>

    <div class="field two">
      <div>
        <div class="lb">1시간 내 반복</div>
        <div class="stepper">
          <button data-step="-1" type="button">−</button><div class="v" id="f-repeat">${F.noise.repeat}</div>
          <button data-step="1" type="button">+</button><span class="unit">회</span>
        </div>
      </div>
      <div>
        <div class="lb">지속 시간</div>
        <div class="stepper">
          <button data-dstep="-5" type="button">−</button><div class="v" id="f-duration-v">${F.noise.duration}</div>
          <button data-dstep="5" type="button">+</button><span class="unit">분</span>
        </div>
      </div>
    </div>

    <div class="summary-card">
      <div class="h">입력 요약</div>
      <div class="v" id="sum"></div>
    </div>

    <div class="cta-bar"><button class="primary-btn" id="submit" type="button">접수</button></div>
    <div class="note-line">앱 측정값입니다. ±3 dB 오차를 감안해 '초과 / 초과 의심'을 나눕니다.</div>`);

  const update = () => {
    const raw = ($("#f-at").value || "").trim();
    const m = raw.match(/^([01]?\d|2[0-3]):([0-5]\d)$/);
    if (m) F.noise.at = `${m[1].padStart(2, "0")}:${m[2]}`;
    F.noise.leq = Number($("#f-leq").value || 0);
    F.noise.lmax = Number($("#f-lmax").value || 0);
    setClock(F.noise.at);
    $("#f-duration-v").textContent = F.noise.duration;
    const typeLabel = F.noise.type === "air" ? "공기전달" : F.noise.type === "out_of_scope" ? "규칙 범위 밖" : "직접충격";
    $("#sum").innerHTML = `${typeLabel} · <em>${F.noise.at}</em> · 최고 <em>${F.noise.lmax} dB</em> · 등가 <em>${F.noise.leq} dB</em> · ${F.noise.repeat}회 · ${F.noise.duration}분`;
  };

  $$("[data-sound]").forEach((b) => b.addEventListener("click", () => {
    $$("[data-sound]").forEach((x) => x.classList.remove("on"));
    b.classList.add("on");
    F.noise.sound = b.dataset.sound;
    F.noise.type = b.dataset.type;
    update();
  }));
  $$("[data-step]").forEach((b) => b.addEventListener("click", () => {
    F.noise.repeat = fmt.clamp(F.noise.repeat + Number(b.dataset.step), 1, 10);
    $("#f-repeat").textContent = F.noise.repeat;
    update();
  }));
  $$("[data-dstep]").forEach((b) => b.addEventListener("click", () => {
    F.noise.duration = fmt.clamp(F.noise.duration + Number(b.dataset.dstep), 5, 60);
    $("#f-duration-v").textContent = F.noise.duration;
    update();
  }));
  $$("[data-preset]").forEach((b) => b.addEventListener("click", () => renderNoiseForm(b.dataset.preset)));
  ["#f-at", "#f-leq", "#f-lmax"].forEach((sel) => {
    $(sel).addEventListener("input", update);
    $(sel).addEventListener("change", update);
    $(sel).addEventListener("blur", () => { $(sel).value = sel === "#f-at" ? F.noise.at : $(sel).value; });
  });
  $("#submit").addEventListener("click", submitNoise);
  bindBack();
  update();
}

/* ────────────────────────────────────────────────────────────
   층간소음 — 접수 → 판정 → 근거 스트림
   ──────────────────────────────────────────────────────────── */
async function submitNoise() {
  const btn = $("#submit");
  btn.disabled = true;
  btn.textContent = "접수 중…";
  try {
    const caseDoc = await api.post("/api/noise/analyze", {
      case_id: "C-003",
      noise_type: F.noise.type,
      sound_label: F.noise.sound,
      at: F.noise.at,
      leq: F.noise.leq,
      lmax: F.noise.lmax,
      repeat_count: F.noise.repeat,
      duration_min: F.noise.duration,
      confidence: 0.94,
      household_context: F.noise.ctx
        ? "다음 날 학교에 가야 하는 아이가 있어 밤 11시 이후에는 조용한 환경이 꼭 필요합니다."
        : "",
    });
    R.noise = { case: caseDoc, refs: [], answer: "", judged: false, letter: null, edited: false, tab: "letter", sent: false };
    renderNoiseResult();
    startStream(caseDoc.id, "noise");
  } catch (err) {
    btn.disabled = false;
    btn.textContent = "접수";
    toast(UI.toast, `접수 실패 — ${err.message}`, 3600);
  }
}

function stepsBar(active, done = []) {
  const labels = [["①", "사실 정리"], ["②", "법령·규약 대조"], ["③", "판정"], ["④", "문서"]];
  return `<div class="steps">${labels.map(([n, t], i) => {
    const cls = done.includes(i) ? "done" : (active === i ? "on" : "");
    return `<div class="step ${cls}"><b>${n}</b>${t}</div>`;
  }).join("")}</div>`;
}

function renderNoiseResult() {
  const { case: c } = R.noise;
  show(`${appBar("접수 완료", { timer: true })}
    <div id="steps">${stepsBar(1, [0])}</div>
    <div class="ev-head">
      <span class="t">법령·규약 근거</span>
      <span class="mode-pill seed" id="modepill">연결 중…</span>
      <span class="api">POST /api/v1/agents/search</span>
    </div>
    <div id="ev-cards"></div>
    <div class="answer-box" id="answer"><span class="caret"></span></div>
    <div id="judge-slot"></div>
    <div id="doc-slot"></div>`);
  startTimer();
  bindBack();
}

function startStream(caseId, kind) {
  if (es) es.close();
  const judged = () => kind === "noise" ? R.noise.judged : R.parking.judged;
  let finished = false;
  const finish = () => {
    if (finished) return;
    finished = true;
    if (!judged()) {
      if (kind === "noise") judgeNoise();
      else judgeParking();
    }
  };
  es = stream(`/api/legal/stream?case_id=${encodeURIComponent(caseId)}`, (ev) => {
    if (ev.type === "mode") setModePill(ev);
    else if (ev.type === "references") addReferences(kind, ev.references || []);
    else if (ev.type === "text-delta") appendAnswer(kind, ev.delta || "");
    else if (ev.type === "error") toast(UI.toast, ev.message || "검색 오류", 3200);
    else if (ev.type === "finish") finish();
  }, () => setTimeout(finish, 400));
  // 안전장치 — 스트림이 끊겨도 8초 뒤 판정은 반드시 보여 준다
  setTimeout(finish, 8000);
}

function setModePill(ev) {
  const pill = $("#modepill");
  if (!pill) return;
  if (ev.mode === "live") {
    pill.className = "mode-pill live";
    pill.textContent = "실시간 Liner API";
    pill.title = ev.endpoint || "";
  } else {
    pill.className = "mode-pill seed";
    pill.textContent = ev.fallback ? "폴백 · 시드" : "데모 시드";
    pill.title = ev.fallback ? "Liner 호출 실패 — 시드 응답으로 대체" : "Liner 응답 포맷 그대로 재생";
  }
}

function addReferences(kind, refs) {
  const holder = $("#ev-cards");
  if (!holder) return;
  const store = kind === "noise" ? R.noise : R.parking;
  if (store.refs.length) return;
  store.refs = refs;
  holder.innerHTML = refs.map((r, i) => `
    <div class="cite-card" style="animation-delay:${i * 70}ms">
      <div class="top">
        <span class="num">${i + 1}</span>
        <span class="doc">${esc(r.title || r.doc || "출처")}</span>
      </div>
      <div class="body">${esc((r.description || r.snippet || "").slice(0, 150))}</div>
      <div class="meta">
        <span>${esc(r.hostname || r.source || "law.go.kr")}</span>
        ${r.date ? `<span>· ${esc(r.date)}</span>` : ""}
        ${r.url ? `<a class="link" href="${esc(r.url)}" target="_blank" rel="noreferrer">원문</a>` : ""}
      </div>
    </div>`).join("");
  const steps = $("#steps");
  if (steps) steps.innerHTML = stepsBar(2, [0, 1]);
}

function appendAnswer(kind, delta) {
  const store = kind === "noise" ? R.noise : R.parking;
  store.answer += delta;
  const box = $("#answer");
  if (!box) return;
  box.innerHTML = `${withCitations(store.answer)}<span class="caret"></span>`;
  box.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

/* ────────────────────────────────────────────────────────────
   판정 카드
   ──────────────────────────────────────────────────────────── */
function barRow(label, measured, threshold, { unit = "dB(A)", digits = 0 } = {}) {
  const scale = Math.max(measured, threshold) * 1.35 || 1;
  const over = measured > threshold;
  const width = Math.min(100, (measured / scale) * 100);
  const mark = Math.min(99, (threshold / scale) * 100);
  return `<div class="bar-row">
    <div class="lab"><span>${label}</span><b>${measured.toFixed(digits)} ${unit}</b></div>
    <div class="bar-track">
      <div class="bar-fill ${over ? "" : "ok"}" style="width:${width}%"></div>
      <div class="bar-mark" style="left:${mark}%"></div>
    </div>
    <div class="bar-note">기준 ${threshold.toFixed(digits)} ${unit} · ${over ? `+${(measured - threshold).toFixed(1)} ${unit}` : "이내"}</div>
  </div>`;
}

function judgeNoise() {
  const { case: c } = R.noise;
  const r = c.result;
  R.noise.judged = true;
  const exceeded = r.result === "기준 초과";
  const leqOver = r.measured.leq_max > r.thresholds.leq;
  const lmaxOver = r.thresholds.lmax !== null && r.measured.lmax_max > r.thresholds.lmax;
  const slot = $("#judge-slot");
  if (!slot) return;
  const steps = $("#steps");
  if (steps) steps.innerHTML = stepsBar(3, [0, 1, 2]);

  const parts = [];
  if (leqOver) parts.push("등가소음도 기준 초과");
  if (lmaxOver) parts.push("최고소음도 기준 초과");
  const sentence = `${r.band} ${parts.length ? parts.join(" · ") : "기준 이내"}.`;
  const ratio = r.margin.pressure_ratio && exceeded ? `음압 약 ${r.margin.pressure_ratio}배` : "기준 이내";

  slot.innerHTML = `<div class="judge ${exceeded ? "danger" : ""}">
    <div class="verdict">
      <div>
        <div class="badge-v ${exceeded ? "" : "ok"}">${esc(r.severity.label)}</div>
        <div class="sub">판정은 코드가 계산 · LLM은 문장만</div>
      </div>
      <div style="margin-left:auto;text-align:right">
        <div style="font-size:24px;font-weight:900;letter-spacing:-.03em">${exceeded ? `+${r.exceeded_db.toFixed(0)}` : "0"}<span style="font-size:12px">dB</span></div>
        <div class="sub">${ratio}</div>
      </div>
    </div>
    <div class="bars">
      ${barRow(`등가소음도 Leq (${r.thresholds.window})`, r.measured.leq_max, r.thresholds.leq)}
      ${r.thresholds.lmax !== null ? barRow("최고소음도 Lmax", r.measured.lmax_max, r.thresholds.lmax) : ""}
    </div>
    <div class="typing-line" id="typing"></div>
    <div class="jfoot">
      <span class="chip-mini" id="cite-jump">근거 ${c.result.citations.length}건</span>
      <span>신뢰도 ${r.confidence.toFixed(2)}</span>
      <span>· 게이트 ${esc(r.gate)}</span>
    </div>
  </div>`;

  typeText($("#typing"), sentence);
  $("#cite-jump")?.addEventListener("click", () => {
    $("#ev-cards")?.scrollIntoView({ behavior: "smooth", block: "center" });
  });
  renderDocTabs("noise");
}

function typeText(node, text, ms = 26) {
  if (!node) return;
  let i = 0;
  node.textContent = "";
  const t = setInterval(() => {
    i += 1;
    node.textContent = text.slice(0, i);
    if (i >= text.length) clearInterval(t);
  }, ms);
}

/* ────────────────────────────────────────────────────────────
   문서 — 조정문 · 보고서
   ──────────────────────────────────────────────────────────── */
function renderDocTabs(kind) {
  const slot = $("#doc-slot");
  if (!slot) return;
  const isNoise = kind === "noise";
  slot.innerHTML = `
    <div class="doc-tabs">
      <button class="doc-tab on" data-tab="letter" type="button">${isNoise ? "조정문" : "알림톡"}</button>
      <button class="doc-tab" data-tab="report" type="button">관리소 보고서</button>
    </div>
    <div id="doc-body"></div>`;
  $$("[data-tab]", slot).forEach((b) => b.addEventListener("click", () => {
    $$("[data-tab]", slot).forEach((x) => x.classList.toggle("on", x === b));
    openTab(kind, b.dataset.tab);
  }));
  openTab(kind, "letter");
}

async function openTab(kind, tab) {
  const holder = $("#doc-body");
  if (!holder) return;
  const store = kind === "noise" ? R.noise : R.parking;
  const caseId = store.case.id;

  if (tab === "letter") {
    holder.innerHTML = letterSkeleton();
    if (!store.letter) {
      try {
        const res = await api.post(`/api/case/${caseId}/letter`, {});
        store.letter = res;
      } catch (err) {
        holder.innerHTML = `<div class="note-line">문서 생성 실패 — ${esc(err.message)}</div>`;
        return;
      }
    }
    holder.innerHTML = letterHtml(kind, store);
    bindLetter(kind, store);
  } else {
    holder.innerHTML = reportSkeleton();
    try {
      const res = await api.post(`/api/case/${caseId}/report`, {});
      store.report = res;
      holder.innerHTML = reportHtml(kind, store, res);
      $("#pdf-btn")?.addEventListener("click", () => {
        window.open(`/print.html?case=${encodeURIComponent(caseId)}&type=report`, "_blank");
      });
    } catch (err) {
      holder.innerHTML = `<div class="note-line">보고서 생성 실패 — ${esc(err.message)}</div>`;
    }
  }
  const steps = $("#steps");
  if (steps) steps.innerHTML = stepsBar(-1, [0, 1, 2, 3]);
}

function skeleton(lines = 4) {
  return `<div class="answer-box">${Array.from({ length: lines }).map(() => '<div style="height:9px;border-radius:5px;background:#eef1f5;margin-bottom:8px"></div>').join("")}</div>`;
}
const letterSkeleton = () => skeleton(5);
const reportSkeleton = () => skeleton(6);

function letterHtml(kind, store) {
  const letter = store.letter?.letter || store.case.letter || "";
  const checks = store.letter?.checks || store.case.checks || [];
  const isNoise = kind === "noise";
  const source = store.letter?.meta?.source === "liner"
    ? `Liner Router · ${esc(store.letter.meta.model)} (${esc(store.letter.meta.routing_strategy)})`
    : "시드 모드 · 결정론적 NVC 템플릿";

  const bodyBlock = isNoise
    ? `<div class="nvc-wrap">
        <div class="nvc-labels">
          <span class="on">사실</span><span>영향·필요</span><span>요청</span><span>부담 낮추기</span>
        </div>
        <div class="letter-box" id="letter" contenteditable="true" spellcheck="false">${esc(letter)}</div>
      </div>
      <div class="edit-badge" id="edit-badge">사용자 수정 1건 · 다음 학습 데이터로</div>`
    : `<div class="alimtalk">
        <div class="bubble">
          <div class="head"><span class="k">T</span>새들마을 3단지 관리사무소 · 알림톡</div>
          <span id="letter" contenteditable="true">${esc(letter)}</span>
        </div>
      </div>
      <div class="reserve-badge" id="reserve">⏱ 30분 후 미이동 시 관리소 보고 예약</div>`;

  return `${bodyBlock}
    <div class="checks" id="checks">
      ${checks.map((c) => `<span class="check ${c.ok ? "ok" : ""}">${c.ok ? "✓" : "·"} ${esc(c.label)}</span>`).join("")}
    </div>
    <div class="doc-actions">
      <button class="primary-btn dark" id="send" type="button">${isNoise ? "익명 전송" : "알림톡 전송"}</button>
      <button class="sub-btn" id="pdf-btn" type="button">PDF</button>
    </div>
    <div class="note-line">${source} · 발송 전 문장은 직접 고칠 수 있습니다</div>`;
}

function bindLetter(kind, store) {
  const box = $("#letter");
  const badge = $("#edit-badge");
  if (box && badge) {
    box.addEventListener("input", () => {
      store.edited = true;
      badge.classList.add("on");
    });
  }
  $("#send")?.addEventListener("click", async () => {
    const btn = $("#send");
    btn.disabled = true;
    try {
      const text = ($("#letter")?.innerText || "").trim();
      store.letter && (store.letter.letter = text);
      const res = await api.post(`/api/case/${store.case.id}/send`, {});
      store.sent = true;
      btn.textContent = kind === "noise" ? "전송 완료" : "발송 완료";
      toast(UI.toast, res.toast + (kind === "parking" ? " · 30분 예약" : ""), 2600);
      const checks = $("#checks");
      if (checks) checks.insertAdjacentHTML("beforeend", '<span class="check ok">✓ 관리소 기록 완료</span>');
    } catch (err) {
      btn.disabled = false;
      toast(UI.toast, `전송 실패 — ${err.message}`, 3200);
    }
  });
  $("#pdf-btn")?.addEventListener("click", () => {
    window.open(`/print.html?case=${encodeURIComponent(store.case.id)}&type=report`, "_blank");
  });
}

function reportHtml(kind, store, res) {
  return `<table class="report-table">
      ${res.fields.map((f) => `<tr><th>${esc(f.label)}</th><td>${esc(f.value)}</td></tr>`).join("")}
    </table>
    <div class="answer-box" style="margin-top:10px">${esc(res.summary || "")}</div>
    <div class="doc-actions">
      <button class="sub-btn" id="pdf-btn" type="button">PDF로 저장</button>
    </div>
    <div class="note-line">${esc(res.title)} · 발행 ${esc(res.issued_at)}</div>`;
}

/* ────────────────────────────────────────────────────────────
   불법·이중주차
   ──────────────────────────────────────────────────────────── */
export function renderParkingForm(preset) {
  if (preset && ZONE_META[preset]) F.parking.preset = preset;
  const meta = ZONE_META[F.parking.preset];
  const photo = F.parking.uploaded || PHOTOS[F.parking.preset][0];
  setClock("19:12");
  show(`${appBar("불법·이중주차 신고")}
    <div class="preset-row">
      <button class="chip preset ${F.parking.preset === "fire" ? "on" : ""}" data-photo="fire" type="button">소방구역 사진</button>
      <button class="chip ${F.parking.preset === "aisle" ? "on" : ""}" data-photo="aisle" type="button">통로 사진</button>
    </div>

    <div class="photo-drop" id="drop">
      <img src="${photo}" alt="현장 사진(가상)">
      <div class="plate-mask">${esc(meta.plate).slice(0, 3)}****</div>
      <div class="scan-line" id="scan"></div>
    </div>
    <div class="photo-strip">
      <div class="th"><img src="${PHOTOS[F.parking.preset][0]}" alt=""><span class="lock">🔒</span></div>
      ${PHOTOS[F.parking.preset][1] ? `<div class="th"><img src="${PHOTOS[F.parking.preset][1]}" alt=""><span class="lock">🔒</span></div>` : ""}
      <div class="th" style="display:grid;place-items:center;background:#fff;border:1.5px dashed #cbd5e1;color:#98a2b3;font-size:18px" id="add-photo">＋</div>
    </div>
    <input type="file" id="file" accept="image/*" class="hidden">

    <div class="detect-row">
      <span class="hot">${esc(meta.label)}</span>
      <span>${esc(meta.location)}</span>
      <span>촬영 19:12</span>
      <span>원본 암호화 · 30일</span>
    </div>

    <div class="field" style="margin-top:12px">
      <div class="lb">위치 유형</div>
      <div class="preset-row" style="margin:8px 0 0">
        ${Object.entries(ZONE_META).map(([k, v]) => `<button class="chip ${k === F.parking.preset ? "on" : ""}" data-zone="${k}" type="button">${esc(v.label)}</button>`).join("")}
      </div>
    </div>

    <div class="summary-card">
      <div class="h">입력 요약</div>
      <div class="v">${esc(meta.label)} · <em>${esc(meta.location)}</em> · ${meta.shots}장</div>
    </div>

    <div class="cta-bar"><button class="primary-btn" id="submit" type="button">접수</button></div>
    <div class="note-line">번호판은 접수 즉시 가운데가 가려집니다 · 원본은 관리자만 열람</div>`);

  setTimeout(() => $("#scan")?.classList.add("hidden"), 2300);
  $$("[data-photo]").forEach((b) => b.addEventListener("click", () => {
    F.parking.uploaded = null;
    renderParkingForm(b.dataset.photo);
  }));
  $$("[data-zone]").forEach((b) => b.addEventListener("click", () => {
    F.parking.uploaded = null;
    renderParkingForm(b.dataset.zone);
  }));
  $("#add-photo")?.addEventListener("click", () => $("#file").click());
  $("#drop")?.addEventListener("click", () => $("#file").click());
  $("#file")?.addEventListener("change", (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      F.parking.uploaded = reader.result;
      renderParkingForm();
      toast(UI.toast, "사진 첨부됨 · 번호판 마스킹 완료", 2000);
    };
    reader.readAsDataURL(file);
  });
  $("#submit").addEventListener("click", submitParking);
  bindBack();
}

async function submitParking() {
  const meta = ZONE_META[F.parking.preset];
  const btn = $("#submit");
  btn.disabled = true;
  btn.textContent = "접수 중…";
  try {
    const caseDoc = await api.post("/api/parking/analyze", {
      case_id: "C-007",
      zone: meta.zone,
      location: meta.location,
      shot_at: "19:12",
      plate_ocr: meta.plate,
      prior_violations_12m: meta.prior,
      confidence: 0.91,
      shots: meta.shots,
      photo_preset: F.parking.preset,
    });
    R.parking = { case: caseDoc, refs: [], answer: "", judged: false, letter: null, edited: false, tab: "letter", sent: false };
    show(`${appBar("접수 완료", { timer: true })}
      <div id="steps">${stepsBar(1, [0])}</div>
      <div class="ev-head">
        <span class="t">법령 근거</span>
        <span class="mode-pill seed" id="modepill">연결 중…</span>
        <span class="api">POST /api/v1/agents/search</span>
      </div>
      <div id="ev-cards"></div>
      <div class="answer-box" id="answer"><span class="caret"></span></div>
      <div id="judge-slot"></div>
      <div id="doc-slot"></div>`);
    startTimer();
    bindBack();
    startStream(caseDoc.id, "parking");
  } catch (err) {
    btn.disabled = false;
    btn.textContent = "접수";
    toast(UI.toast, `접수 실패 — ${err.message}`, 3600);
  }
}

function judgeParking() {
  const { case: c } = R.parking;
  const r = c.result;
  R.parking.judged = true;
  const slot = $("#judge-slot");
  if (!slot) return;
  const steps = $("#steps");
  if (steps) steps.innerHTML = stepsBar(3, [0, 1, 2]);

  slot.innerHTML = `<div class="judge danger">
    <div class="verdict">
      <div>
        <div class="badge-v">${esc(r.severity.label)}</div>
        <div class="sub">${esc(r.location)} · 촬영 ${esc((r.shot_at || "").slice(11, 16))}</div>
      </div>
      <div style="margin-left:auto;text-align:right">
        <div style="font-size:26px;font-weight:900;letter-spacing:-.03em;white-space:nowrap">${r.fine ? fmt.won(r.fine) : "규정 없음"}</div>
        <div class="sub" style="white-space:nowrap">${r.fine ? "재범 시 100만 원" : "관리규약 조치"}</div>
      </div>
    </div>
    <div class="typing-line" id="typing"></div>
    <div class="gate-note">「사이」는 판정 보조 도구입니다. 처분 권한은 ${esc(r.authority)}에 있습니다.</div>
    <div class="jfoot">
      <span class="chip-mini" id="cite-jump">근거 ${r.citations.length}건</span>
      <span>신뢰도 ${r.confidence.toFixed(2)}</span>
      <span>· ${esc(r.plate_masked)}</span>
    </div>
    <button class="sub-btn" id="to-twin" type="button" style="margin-top:10px">3D로 보기 — 끊긴 소방 동선</button>
  </div>`;

  typeText($("#typing"), `${r.zone_label} · 즉시 이동 요청 대상.`);
  $("#cite-jump")?.addEventListener("click", () => $("#ev-cards")?.scrollIntoView({ behavior: "smooth", block: "center" }));
  $("#to-twin")?.addEventListener("click", () => window.dispatchEvent(new CustomEvent("sai:view", { detail: { view: "twin", focus: true } })));
  renderDocTabs("parking");
}

/* ────────────────────────────────────────────────────────────
   리허설 · 초기화
   ──────────────────────────────────────────────────────────── */
export function rehearse(kind) {
  if (kind === "noise") renderNoiseForm("case3");
  else if (kind === "parking") { F.parking.preset = "fire"; F.parking.uploaded = null; renderParkingForm(); }
  else reset();
}

export function reset() {
  if (es) { es.close(); es = null; }
  stopTimer();
  F.noise = { at: "23:20", leq: 37, lmax: 58, repeat: 3, duration: 20, sound: "발소리", type: "impact", ctx: true };
  F.parking = { preset: "fire", uploaded: null };
  R.noise = null; R.parking = null;
  renderHome();
}

export function initMobile() {
  UI.body = document.getElementById("screen-body");
  UI.toast = document.getElementById("toast");
  UI.clock = document.getElementById("clock");
  renderHome();
}
