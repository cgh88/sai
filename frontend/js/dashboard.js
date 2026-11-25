// 뷰 4 — 관리사무소 통합 관제 대시보드
import { api, esc, countUp, fmt, toast } from "./api.js";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

let selected = "C-003";
let lastDashboard = null;

const ST_CLASS = { "승인 대기": "승인-대기", "발송 완료": "발송-완료", "처리 완료": "처리-완료", "검토 대기": "검토-대기", "이동 요청 발송": "이동-요청-발송" };

export async function initDashboard(force = false) {
  if (lastDashboard && !force) return render(lastDashboard);
  try {
    const data = await api.get("/api/dashboard");
    lastDashboard = data;
    render(data);
  } catch (err) {
    toast(document.getElementById("toast"), `대시보드 로드 실패 — ${err.message}`, 3000);
  }
}

function render(data) {
  lastDashboard = data;
  $("#cnt-today").textContent = data.counts.today;
  $("#cnt-pending").textContent = data.counts.pending;
  $("#dash-updated").textContent = `갱신 ${data.generated_at.replace("T", " ").slice(11, 16)} · 가상 데이터`;

  $("#kpis").innerHTML = data.kpis.map((k) => `
    <div class="kpi" data-key="${k.key}">
      <div class="lb">${esc(k.label)} <span class="basis">${esc(k.basis)}</span></div>
      <div class="v"><span class="from">${esc(k.from)}</span><span class="to" data-to="${k.to_value}">0</span><span class="unit">${esc(k.unit)}</span>
        ${k.delta_pct ? `<span class="delta">${k.delta_pct}%</span>` : ""}</div>
      <div class="note">${esc(k.note)}</div>
    </div>`).join("");
  $$("#kpis .to").forEach((node) => {
    const to = Number(node.dataset.to);
    countUp(node, to, { dec: to % 1 === 0 ? 0 : 1, ms: 1100 });
    setTimeout(() => { node.textContent = to % 1 === 0 ? String(to) : to.toFixed(1); }, 1200);
  });

  $("#case-rows").innerHTML = data.cases.map((c) => `
    <tr data-id="${esc(c.id)}" class="${c.id === selected ? "sel" : ""}">
      <td><div class="id">${esc(c.id)}</div><div class="sub-t">${esc(c.received_at)}</div></td>
      <td>${esc(c.kind_label)}</td>
      <td>${esc(c.target)}</td>
      <td><span class="urg ${esc(c.urgency)}">${esc(c.urgency)}</span></td>
      <td><span class="stt ${ST_CLASS[c.status] || ""}">${esc(c.status)}</span><div class="sub-t">${esc(c.gate)}</div></td>
      <td>${c.citations}건<div class="sub-t">신뢰 ${c.confidence.toFixed(2)}</div></td>
      <td>${c.processing_min}분</td>
    </tr>`).join("");
  $$("#case-rows tr").forEach((tr) => tr.addEventListener("click", () => {
    selected = tr.dataset.id;
    $$("#case-rows tr").forEach((x) => x.classList.toggle("sel", x === tr));
    loadDetail(selected);
  }));

  $("#log-list").innerHTML = data.citation_log.map((l) => `
    <div class="log-row">
      <span class="tm">${esc((l.at || "").slice(11, 16) || l.at)}</span>
      <span class="cid">${esc(l.case_id)}</span>
      <span class="docs">${esc((l.docs || []).join(" · ").slice(0, 70))}</span>
      <span class="n">${l.citations}건 · ${esc(l.event || "검색")}</span>
    </div>`).join("");

  $("#brief-rows").innerHTML = data.briefing.map((b) => `
    <div class="brief-row"><span class="l">${esc(b.label)}</span><span class="v">${esc(b.value)}</span><span class="n">${esc(b.note)}</span></div>`).join("");

  loadDetail(selected);
}

async function loadDetail(caseId) {
  const holder = $("#detail");
  if (!holder) return;
  try {
    const c = await api.get(`/api/case/${caseId}`);
    const r = c.result;
    const cites = (r.citations || []).map((x, i) => `
      <div class="cite-mini"><span class="n">${i + 1}</span>
        <div class="d"><b>${esc(x.doc)}</b> ${esc(x.article)} <span>· 시행 ${esc(x.effective)} · ${esc(x.source)}</span></div></div>`).join("");
    const headline = r.kind === "noise"
      ? `${r.band} · 등가 ${r.measured.leq_max} / 최고 ${r.measured.lmax_max} dB(A) → ${r.result}`
      : `${r.zone_label} · ${r.plate_masked} → ${r.result}`;
    holder.innerHTML = `
      <div class="panel-head"><span class="t">${esc(c.id)}</span>
        <span class="s">${esc(c.status)} · ${esc(c.assignee || "관리소")}</span></div>
      <div class="body">
        <div class="case-id">${esc(r.kind === "noise" ? "층간소음" : "불법·이중주차")} · ${esc(c.payload.unit ? `→ ${esc(c.payload.unit.to)}호` : esc(r.zone_label))}</div>
        <h3>${esc(headline)}</h3>
        <div class="meta">접수 ${esc(c.received_at.replace("T", " "))} · 게이트 ${esc(r.gate)} · 신뢰도 ${esc(String(c.result.confidence.toFixed(2)))}</div>

        <div class="sec"><div class="h">근거 ${r.citations.length}건 (Liner Search 인용)</div>${cites}</div>
        <div class="sec"><div class="h">조정문 초안 (${c.letter_source === "liner" ? "Liner Router" : "시드 · NVC 템플릿"})</div>
          <div class="draft">${esc((c.letter || "").slice(0, 320))}${(c.letter || "").length > 320 ? "…" : ""}</div></div>
        <div class="actions">
          <button class="btn primary" data-act="approve">승인</button>
          <button class="btn" data-act="hold">보류</button>
          <button class="btn" data-act="pdf">PDF</button>
        </div>
      </div>`;
    $$("[data-act]", holder).forEach((b) => b.addEventListener("click", async () => {
      const act = b.dataset.act;
      if (act === "pdf") {
        window.open(`/print.html?case=${encodeURIComponent(c.id)}&type=report`, "_blank");
        return;
      }
      b.disabled = true;
      try {
        const res = await api.post(`/api/case/${c.id}/action`, { action: act });
        lastDashboard = res.dashboard;
        render(res.dashboard);
      } catch (err) {
        b.disabled = false;
        toast(document.getElementById("toast"), `처리 실패 — ${err.message}`, 3000);
      }
    }));
  } catch (err) {
    holder.innerHTML = `<div class="empty">불러오기 실패 — ${esc(err.message)}</div>`;
  }
}

export function initDashboardEvents() {
  $("#dash-refresh")?.addEventListener("click", () => initDashboard(true));
  $("#print-brief")?.addEventListener("click", () => window.open("/print.html?type=brief", "_blank"));
}
