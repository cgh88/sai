// 셸 — 뷰 전환 · 상태 배지 · 키보드 · 3D 컨트롤
import { api, state, loadConfig, modeBadge } from "./api.js";
import { initSlides, next as slideNext, prev as slidePrev } from "./slides.js";
import { initMobile, rehearse, reset as resetMobile } from "./mobile.js";
import { initDashboard, initDashboardEvents } from "./dashboard.js";

const VIEWS = ["slides", "mobile", "twin", "dashboard"];
let twinHud = true;

function twinUrl() {
  return `/3d_viewer.html${twinHud ? "" : "?hud=0"}`;
}

/** 숨은 뷰에서 WebGL 을 계속 그리지 않도록, 3D 는 볼 때만 로드한다(녹화 중 CPU 확보). */
function ensureTwin(load) {
  const frame = document.getElementById("twin");
  if (!frame) return;
  if (load) {
    if (frame.dataset.state !== "on") {
      frame.src = twinUrl();
      frame.dataset.state = "on";
    }
  } else if (frame.dataset.state === "on") {
    frame.src = "about:blank";
    frame.dataset.state = "off";
  }
}

function focusTwin() {
  const frame = document.getElementById("twin");
  frame?.contentWindow?.focus();
  frame?.focus();
}

function setView(name, { focus3d = false } = {}) {
  if (!VIEWS.includes(name)) return;
  state.view = name;
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.view === name));
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${name}`));
  ensureTwin(name === "twin");
  if (name === "dashboard") initDashboard();
  if (name === "twin" && focus3d) setTimeout(focusTwin, 2600);
}

function bindTwin() {
  document.getElementById("twin-focus")?.addEventListener("click", focusTwin);
  document.getElementById("twin-hud")?.addEventListener("click", (e) => {
    twinHud = !twinHud;
    const frame = document.getElementById("twin");
    if (frame && frame.dataset.state === "on") frame.src = twinUrl();
    e.currentTarget.textContent = twinHud ? "HUD 끄기" : "HUD 켜기";
    const mode = document.getElementById("twin-mode");
    if (mode) mode.textContent = twinHud ? "기본 HUD" : "?hud=0 촬영 모드";
  });
  document.getElementById("twin-reload")?.addEventListener("click", () => {
    const frame = document.getElementById("twin");
    if (frame) { frame.src = twinUrl(); frame.dataset.state = "on"; }
  });
}

async function boot() {
  initSlides();
  initMobile();
  bindTwin();
  initDashboardEvents();

  document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => setView(t.dataset.view)));
  window.addEventListener("sai:view", (e) => setView(e.detail.view, { focus3d: !!e.detail.focus }));

  document.querySelectorAll("[data-rehearse]").forEach((b) => b.addEventListener("click", async () => {
    const kind = b.dataset.rehearse;
    if (kind === "reset") {
      await api.post("/api/demo/reset", {});
      resetMobile();
      await initDashboard(true);
      return;
    }
    rehearse(kind);
  }));

  document.addEventListener("keydown", (e) => {
    const tag = (e.target.tagName || "").toLowerCase();
    const typing = tag === "input" || tag === "textarea" || e.target.isContentEditable;

    if (e.altKey && /^[1-4]$/.test(e.key)) {
      e.preventDefault();
      setView(VIEWS[Number(e.key) - 1]);
      return;
    }
    if (typing) return;
    if (state.view === "slides" && e.key === "ArrowRight") { e.preventDefault(); slideNext(); }
    if (state.view === "slides" && e.key === "ArrowLeft") { e.preventDefault(); slidePrev(); }
    if ((e.key === "r" || e.key === "R") && !e.altKey) {
      api.post("/api/demo/reset", {}).then(() => { resetMobile(); initDashboard(true); });
    }
  });

  try {
    await loadConfig();
    modeBadge(document.getElementById("badge-mode"));
    const keyBadge = document.getElementById("badge-key");
    if (keyBadge) {
      keyBadge.textContent = state.health?.liner?.liner_key_configured ? "키 서버 보관" : "키 노출 0";
      keyBadge.title = "LINER_API_KEY 는 서버 .env 에서만 읽고 화면·응답에 담지 않습니다";
    }
    const rules = document.getElementById("badge-rules");
    if (rules && state.health?.rules) rules.textContent = `룰 엔진 v${state.health.rules.version}`;
  } catch (err) {
    const badge = document.getElementById("badge-mode");
    if (badge) { badge.className = "badge fallback"; badge.textContent = "서버 연결 실패"; }
  }
}

boot();
