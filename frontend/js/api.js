// 공통 API · 상태 · 포맷터
export const state = {
  config: null,
  health: null,
  mode: "seed",           // seed | live
  view: "slides",
  selectedCase: null,
  listeners: new Set(),
};

export function onChange(fn) { state.listeners.add(fn); }
export function emit(name, data) {
  window.dispatchEvent(new CustomEvent(name, { detail: data }));
}

async function json(res) {
  if (!res.ok) {
    let detail = res.statusText;
    try { const body = await res.json(); detail = body.detail || body.message || detail; } catch { /* noop */ }
    throw new Error(`${res.status} ${detail}`);
  }
  return res.json();
}

export const api = {
  get: (path) => fetch(path, { headers: { Accept: "application/json" } }).then(json),
  post: (path, body) => fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  }).then(json),
};

export const fmt = {
  db: (v) => (v === null || v === undefined ? "–" : `${Number(v).toFixed(v % 1 === 0 ? 0 : 1)}`),
  won: (v) => `${Math.round((v || 0) / 10000)}만 원`,
  pct: (v) => `${v}%`,
  hhmm: (iso) => (iso || "").replace("T", " ").slice(-5),
  date: (iso) => (iso || "").slice(5, 10).replace("-", "/"),
  clamp: (v, a, b) => Math.min(b, Math.max(a, v)),
};

export function esc(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

/** 본문의 [1] [2] 인용 번호를 위첨자 배지로 */
export function withCitations(text) {
  return esc(text).replace(/\[(\d{1,2})\]/g, '<span class="cite">[$1]</span>');
}

export function countUp(node, to, { dec = 0, ms = 1200 } = {}) {
  const from = 0;
  const start = performance.now();
  const step = (now) => {
    const t = Math.min(1, (now - start) / ms);
    const eased = 1 - Math.pow(1 - t, 3);
    const value = from + (to - from) * eased;
    node.textContent = dec ? value.toFixed(dec) : Math.round(value).toLocaleString("ko-KR");
    if (t < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

/** Liner SSE 중계 — 브라우저 EventSource(GET) */
export function stream(url, onEvent, onError) {
  const es = new EventSource(url);
  es.onmessage = (ev) => {
    if (!ev.data) return;
    try { onEvent(JSON.parse(ev.data)); } catch { /* ignore partial */ }
  };
  es.onerror = () => {
    // 정상 종료(finish 후 서버 close)도 error 로 떨어진다 — 한 번만 알리고 닫는다.
    es.close();
    onError && onError();
  };
  return es;
}

export async function loadConfig() {
  if (state.config) return state.config;
  const [config, health] = await Promise.all([api.get("/api/config"), api.get("/api/health")]);
  state.config = config;
  state.health = health;
  state.mode = health.liner.mode;
  return config;
}

export function modeBadge(el) {
  if (!el) return;
  const h = state.health || {};
  const liner = h.liner || {};
  if (state.mode === "live") {
    const bal = liner.balance_usd ? ` · 잔액 $${Number(liner.balance_usd).toFixed(2)}` : "";
    el.className = "badge live";
    el.innerHTML = `<span class="dot"></span>실시간 Liner API${bal}`;
  } else {
    el.className = "badge seed";
    el.innerHTML = `<span class="dot"></span>데모 시드 모드`;
    el.title = "LINER_API_KEY 미설정 — Liner Search Agent 응답 포맷 그대로 재생";
  }
}

export function toast(el, message, ms = 2200) {
  if (!el) return;
  el.textContent = message;
  el.classList.add("on");
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.remove("on"), ms);
}
