/* Deal Darwin web app: shared state, API, navigation and small UI helpers. */
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const pct = x => Math.round(x * 100) + "%";
const money = x => "$" + Math.round(x).toLocaleString("en-US");
const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
const rk = n => `var(--r${Math.min(5, Math.max(1, Math.round(n)))})`;   // theme-aware risk colour (RGB triple)
const riskPill = n => n == null ? `<span class="pill pend">·</span>`
  : `<span class="pill risk" style="--rc:${rk(n)}" title="risk ${n} of 5">${n}</span>`;
const LOGO = (size = 28) => `<svg class="mark" width="${size}" height="${size}" viewBox="0 0 32 32" aria-hidden="true">
  <path d="M16 24V17M16 17l-5.2-5.6M16 17l5.2-5.6" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="16" cy="25.5" r="2.6" fill="currentColor"/>
  <circle cx="9.5" cy="9.5" r="2.8" fill="var(--bg)" stroke="currentColor" stroke-width="2.2"/>
  <circle cx="22.5" cy="9.5" r="3" fill="var(--accent)"/></svg>`;
const THEME_ICON = {dark: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/></svg>`,
  light: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>`};
function setThemeButton() {
  const dark = document.documentElement.dataset.theme === "dark";
  $("#theme").innerHTML = dark ? THEME_ICON.light : THEME_ICON.dark;
  $("#theme").setAttribute("aria-pressed", dark); $("#theme").title = dark ? "Light mode" : "Dark mode";
}
const STATUS = {found: "found", ambiguous: "ambiguous", not_found: "missing"};
const ICON = {
  check: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="M5 12l5 5 9-10"/></svg>`,
  x: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="M6 6l12 12M18 6L6 18"/></svg>`,
  up: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M12 16V4m0 0-5 5m5-5 5 5M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"/></svg>`,
};

/* ---------- state ---------- */
const S = {
  view: "welcome", jobId: null, analysis: null, live: null, stages: {}, error: null,
  asks: [], neg: null, offerSel: 0, creative: {items: [], sel: null}, meta: null,
};
const VIEWS = {};            // name -> render()
const NEEDS_CONTRACT = new Set(["overview", "ask", "negotiate", "pack"]);   // these show an empty state without one
const SAMPLES = {   // example contracts; descriptions shortened from contracts/contracts_index.csv
  A: {label: "Fair deal", parties: "Northwind × Maya", desc: "Close to the brand's playbook"},
  B: {label: "Predatory deal", parties: "Vela × Priya", desc: "Eight traps, each stated plainly"},
  C: {label: "Buried terms", parties: "Kettle × Jordan", desc: "Friendly, but traps hide in definitions"},
  D: {label: "Messy scan", parties: "Northwind × Diego", desc: "Scanned printout with handwritten changes"},
};
const stripExt = n => String(n || "").replace(/\.(pdf|png|jpe?g|webp)$/i, "");
const displayName = a => (a && a.sample && SAMPLES[a.sample] ? SAMPLES[a.sample].label : a ? stripExt(a.name) : "");
const EMPTY_ICON = {
  ask: `<svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"><path d="M4 5h16v11H9l-5 4z"/><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .8-1 1.4"/><circle cx="12" cy="14.6" r=".6" fill="currentColor"/></svg>`,
  negotiate: `<svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 17l5-5 4 4 7-8"/><path d="M15 8h5v5"/></svg>`,
  pack: `<svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"><path d="M6 3h9l4 4v14H6z"/><path d="M15 3v4h4M9 12h7M9 16h5"/></svg>`,
};
function pageHead(title, purpose, extra = "") {
  return `<div class="head"><div><h1>${title}</h1><p class="purpose">${purpose}</p></div><span class="sp"></span>${extra}</div>`;
}
function noContract(view, title, purpose, sentence) {
  $("#view").innerHTML = `<section class="screen">${pageHead(title, purpose)}
    <div class="empty big-empty">${EMPTY_ICON[view] || ""}<p>${sentence}</p>
      <div class="askrow" style="justify-content:center"><button class="btn" data-act="upload">Upload a contract</button><button class="btn ghost" data-act="example">Try an example</button></div></div></section>`;
  $("#view").querySelector('[data-act="upload"]').addEventListener("click", () => { go("welcome"); const f = $("#file"); if (f) f.click(); });
  $("#view").querySelector('[data-act="example"]').addEventListener("click", () => { go("welcome"); const ex = $("#examples"); if (ex) { ex.scrollIntoView({behavior: reduced ? "auto" : "smooth", block: "center"}); ex.querySelector("button").focus({preventScroll: true}); } });
}

/* ---------- API ---------- */
async function api(url, body) {
  const opt = body instanceof FormData ? {method: "POST", body}
    : body ? {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)} : {};
  let r;
  try { r = await fetch(url, opt); } catch (e) { throw new Error("Can't reach the server. Is app/server.py running?"); }
  const j = await r.json().catch(() => ({}));
  if (!r.ok && r.status !== 202) throw new Error(j.error || `HTTP ${r.status}`);
  return j;
}
function stream(jobId, onEvent) {
  return new Promise(resolve => {
    const es = new EventSource(`/api/events/${jobId}`);
    es.onmessage = e => { try { onEvent(JSON.parse(e.data)); } catch (err) { console.error(err); } };
    es.addEventListener("end", () => { es.close(); resolve(); });
    es.onerror = () => { if (es.readyState === 2) resolve(); };
  });
}

/* ---------- navigation ---------- */
function go(view) {
  if (view === "overview" && !S.analysis) view = "welcome";   // other tabs show their own empty state
  const changed = S.view !== view;
  S.view = view;
  render();
  $("#view").scrollTop = 0;
  if (changed && view !== "ask") $("#view").focus({preventScroll: true});  // keyboard users land in the new screen
}
function render() {
  document.querySelectorAll("#side button").forEach(b => {
    const v = b.dataset.view, cur = v === S.view || (v === "overview" && ["welcome", "processing"].includes(S.view));
    b.setAttribute("aria-current", cur ? "page" : "false");
    b.disabled = false;
  });
  const a = S.analysis;
  const p = a && a.parties ? [a.parties.brand_name, a.parties.creator_name].filter(Boolean).join(" × ") : "";
  $("#cname").innerHTML = a ? `<b>${esc(displayName(a))}</b>${p ? ` · ${esc(p)}` : ""}` : S.view === "processing" && S.live ? `<b>${esc(S.live.name)}</b>` : "";
  $("#newc").hidden = !a && S.view !== "processing";
  (VIEWS[S.view] || VIEWS.welcome)();
}
function sideBadge() { /* sidebar stays clean: live/cached status is shown on each page instead */ }
function newContract() {
  Object.assign(S, {jobId: null, analysis: null, live: null, stages: {}, error: null, asks: [], neg: null, offerSel: 0});
  document.querySelectorAll("#side em").forEach(e => { e.className = "bd"; e.textContent = ""; });
  go("welcome");
}

/* ---------- helpers ---------- */
const fill = root => requestAnimationFrame(() => requestAnimationFrame(() =>
  root.querySelectorAll("[data-w]").forEach(el => { el.style.width = el.dataset.w; })));
const track = (v, cls = "") => `<span class="track ${cls}"><i data-w="${Math.max(0, Math.min(1, v || 0)) * 100}%"></i></span>`;
function ringHTML(r) {
  const R = 72, C = 2 * Math.PI * R;
  return `<div class="ring"><svg viewBox="0 0 168 168" role="img" aria-label="Overall risk ${r ?? "pending"} of 5">
    <circle class="bg" cx="84" cy="84" r="${R}"/><circle class="fg" cx="84" cy="84" r="${R}" style="stroke:${r ? `rgb(${rk(r)})` : "transparent"}"
    stroke-dasharray="${C}" stroke-dashoffset="${C}" data-off="${r ? C * (1 - r / 5) : C}"/></svg>
    <div class="c"><b class="num">${r == null ? "—" : r.toFixed(1)}</b><span>risk / 5</span></div></div>`;
}
const animateRing = root => requestAnimationFrame(() => requestAnimationFrame(() =>
  root.querySelectorAll(".ring .fg").forEach(c => { c.style.strokeDashoffset = c.dataset.off; })));
function dropTarget(el, onFiles) {
  ["dragenter", "dragover"].forEach(t => el.addEventListener(t, e => { e.preventDefault(); el.classList.add("over"); }));
  ["dragleave", "drop"].forEach(t => el.addEventListener(t, e => { e.preventDefault(); el.classList.remove("over"); }));
  el.addEventListener("drop", e => e.dataTransfer.files.length && onFiles([...e.dataTransfer.files]));
}
const usage = m => m >= 999 ? "perpetual" : m + " mo";
const excl = m => m === 0 ? "none" : m + " mo";
const revs = r => r >= 99 ? "unlimited rev" : r + " rev";
const phrase = o => `Fee ${pct(o.fee_mult)}, usage ${usage(o.usage_months)}, excl ${excl(o.excl_months)}, net-${o.net_days}, ${o.kill_pct}% kill fee, ${revs(o.revisions)}`;

document.addEventListener("keydown", e => {  // Escape collapses an open clause row
  if (e.key === "Escape") document.querySelectorAll(".row.open").forEach(r => { r.classList.remove("open"); r.querySelector("button").setAttribute("aria-expanded", "false"); });
});

function boot() {
  $("#home").innerHTML = LOGO(28) + "<span>Deal Darwin</span>";
  setThemeButton();
  $("#theme").addEventListener("click", () => {
    const dark = document.documentElement.dataset.theme !== "dark";
    if (dark) document.documentElement.dataset.theme = "dark"; else delete document.documentElement.dataset.theme;
    try { localStorage.setItem("dd-theme", dark ? "dark" : "light"); } catch (e) { /* private mode: theme just isn't remembered */ }
    setThemeButton();
  });
  $("#side").addEventListener("click", e => { const b = e.target.closest("button"); if (b && !b.disabled) go(b.dataset.view); });
  $("#newc").addEventListener("click", newContract);
  $("#home").addEventListener("click", () => go(S.analysis ? "overview" : "welcome"));
  api("/api/meta").then(m => { S.meta = m; }).catch(() => {});
  render();
  const qs = new URLSearchParams(location.search), s = qs.get("sample");  // demo links: ?sample=C&view=ask&ask=...
  S.afterView = qs.get("view"); S.afterAsk = qs.get("ask"); S.afterRun = qs.get("run") === "1";
  if (s && /^[A-D]$/i.test(s)) startAnalysis(null, s.toUpperCase());
  const job = qs.get("job");   // reopen a finished analysis: ?job=<id>
  if (job && /^[0-9a-f]{6,32}$/.test(job)) api(`/api/result/${job}`).then(res => {
    if (!res.clauses) return;
    S.analysis = {...res, jobId: job};
    go(S.afterView && VIEWS[S.afterView] ? S.afterView : "overview");
    if (S.afterAsk) { sendAsk(S.afterAsk, "auto", []); S.afterAsk = null; }
    if (S.afterRun && S.view === "negotiate") { S.afterRun = false; runNegotiation(); }
  }).catch(e => { S.error = e.message; render(); });
}
