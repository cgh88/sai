// 뷰 1 — 슬라이드 덱 (도입 · 아키텍처 · 원가 · 성과 · 로드맵)
import { countUp } from "./api.js";

let slides = [];
let dots = [];
let index = 0;
let locked = false;

function animate(slide) {
  slide.querySelectorAll("[data-count]").forEach((node) => {
    const to = Number(node.dataset.count);
    const dec = Number(node.dataset.dec || 0);
    countUp(node, to, { dec, ms: dec ? 1400 : 1200 });
  });
  const donut = slide.querySelector("#donut-val");
  if (donut) {
    const c = 2 * Math.PI * 100;
    donut.style.strokeDasharray = `${c}`;
    donut.style.strokeDashoffset = `${c}`;
    requestAnimationFrame(() => {
      setTimeout(() => { donut.style.strokeDashoffset = `${c * (1 - 0.539)}`; }, 60);
    });
  }
  if (slide.dataset.anim === "s3") {
    slide.querySelectorAll(".arrow3 span").forEach((s, i) => {
      setTimeout(() => s.classList.add("on"), 300 + i * 380);
    });
  }
}

export function go(i) {
  if (!slides.length) return;
  index = (i + slides.length) % slides.length;
  slides.forEach((s, k) => s.classList.toggle("on", k === index));
  dots.forEach((d, k) => d.classList.toggle("on", k === index));
  const count = document.getElementById("deck-count");
  if (count) count.textContent = `${index + 1} / ${slides.length}`;
  animate(slides[index]);
}

export function next() { go(index + 1); }
export function prev() { go(index - 1); }
export function current() { return index; }

export function initSlides() {
  slides = Array.from(document.querySelectorAll("#deck .slide"));
  const holder = document.getElementById("deck-dots");
  dots = slides.map((_, i) => {
    const b = document.createElement("button");
    b.className = "dot-btn" + (i === 0 ? " on" : "");
    b.setAttribute("aria-label", `${i + 1}번 슬라이드`);
    b.addEventListener("click", () => go(i));
    holder.appendChild(b);
    return b;
  });
  document.getElementById("deck-prev")?.addEventListener("click", prev);
  document.getElementById("deck-next")?.addEventListener("click", next);

  // 휠로 넘기기 — 녹화 중 실수 방지를 위해 700ms 잠금
  const view = document.getElementById("view-slides");
  view.addEventListener("wheel", (e) => {
    if (locked) return;
    if (Math.abs(e.deltaY) < 24) return;
    locked = true;
    setTimeout(() => { locked = false; }, 700);
    if (e.deltaY > 0) next(); else prev();
  }, { passive: true });

  go(0);
}
