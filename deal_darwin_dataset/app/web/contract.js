/* Welcome -> Processing -> Overview. */
const STEPS = [["reading", "Reading the contract", "NDI"], ["rating", "Rating risk", "Drex"], ["good", "Finding the good parts", ""]];

const HOW = [
  ["Read", "Pulls out fee, usage, exclusivity, payment and kill fee, with the page each came from.",
   `<path d="M6 3h9l4 4v14H6z"/><path d="M15 3v4h4M9 12h7M9 16h5"/>`],
  ["Rate", "Scores the risk of every term.", `<circle cx="12" cy="12" r="8"/><path d="M12 8v4l3 2"/>`],
  ["Counter", "Searches hundreds of offers and ranks them by chance of acceptance and value to you.", `<path d="M4 17l5-5 4 4 7-8"/><path d="M15 8h5v5"/>`],
  ["Create", "Checks campaign visuals against the brand's rules.", `<rect x="4" y="4" width="16" height="16" rx="3"/><circle cx="9" cy="10" r="1.6"/><path d="M5 18l5-5 4 4 2-2 3 3"/>`],
];

VIEWS.welcome = () => {
  $("#view").innerHTML = `<section class="welcome">
    <div class="hero-mark">${LOGO(40)}<span>Deal Darwin</span></div>
    <div class="hero">
      <h1>Know what you're signing.<br><span>Negotiate what you're worth.</span></h1>
      <p>Upload a creator-brand contract. Deal Darwin reads it, rates the risks, and finds a counter-offer the brand will actually accept.</p>
    </div>
    <label class="drop" id="drop" tabindex="0">
      <input type="file" id="file" accept="application/pdf,.pdf,image/png,image/jpeg,image/webp" multiple hidden>
      ${ICON.up}<b>Drop a PDF or screenshots</b><small>or click to choose</small>
    </label>
    <p class="err" id="werr" role="alert">${esc(S.error || "")}</p>
    <div class="examples" id="examples"><h2>Or try an example</h2>
      <div class="excards">${Object.entries(SAMPLES).map(([id, x]) => `<button class="excard" data-s="${id}">
        <b>${esc(x.label)}</b><span class="parties">${esc(x.parties)}</span><span class="muted">${esc(x.desc)}</span></button>`).join("")}</div></div>
    <div class="how"><h2>How it works</h2>
      <ol class="howcards">${HOW.map(([t, d, ic], i) => `<li class="howcard"><svg viewBox="0 0 24 24" aria-hidden="true">${ic}</svg>
        <b><span class="faint">${i + 1}</span> ${t}</b><span class="muted">${d}</span></li>`).join("")}</ol></div>
  </section>`;
  const drop = $("#drop");
  $("#file").addEventListener("change", e => e.target.files.length && startAnalysis([...e.target.files]));
  drop.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("#file").click(); } });
  dropTarget(drop, startAnalysis);
  document.querySelectorAll(".excard").forEach(b => b.addEventListener("click", () => startAnalysis(null, b.dataset.s)));
};

async function startAnalysis(files, sample) {
  const fd = new FormData();
  if (files) files.forEach(f => fd.append("file", f, f.name)); else fd.append("sample", sample);
  S.error = null;
  Object.assign(S, {analysis: null, asks: [], neg: null, offerSel: 0});   // never show the previous contract while reading a new one
  S.live = {name: files ? stripExt(files[0].name) + (files.length > 1 ? ` +${files.length - 1}` : "") : SAMPLES[sample].label,
            clauses: {}, overall: null, summary: null, extraction: null, parties: null, t0: Date.now()};
  startReadTimer();
  S.stages = {};
  go("processing");
  try {
    const j = await api("/api/analyze", fd);
    S.jobId = j.job_id;
    await stream(j.job_id, onAnalyzeEvent);
    const res = await api(`/api/result/${j.job_id}`);
    if (!res.clauses) {
      const bad = Object.values(S.stages).find(st => st.status === "error");
      throw new Error(bad ? `Couldn't finish ${bad.stage === "reading" ? "reading" : "rating"} this contract: ${bad.error || "unknown error"}` : "Analysis did not finish.");
    }
    S.analysis = {...res, jobId: j.job_id};
    setTimeout(() => {
      go(S.afterView && VIEWS[S.afterView] ? S.afterView : "overview");
      if (S.afterAsk && typeof sendAsk === "function") { sendAsk(S.afterAsk, "auto", []); S.afterAsk = null; }
    }, reduced ? 0 : 500);
  } catch (e) {
    S.error = e.message; S.live = null; go("welcome");
  }
}

function onAnalyzeEvent(ev) {
  const L = S.live; if (!L) return;
  if (ev.type === "stage") { S.stages[ev.stage] = ev; if (ev.stage === "reading" && ev.status !== "running") L.readSecs = Math.round((Date.now() - L.t0) / 1000); }
  if (ev.type === "stage" && ev.reset && ev.stage === "rating") Object.values(L.clauses).forEach(c => { c.risk = null; });
  if (ev.type === "meta") { L.parties = ev.parties; L.extraction = ev.extraction; }
  if (ev.type === "clause") L.clauses[ev.clause.key] = ev.clause;
  if (ev.type === "overall") L.overall = ev.overall_risk;
  if (ev.type === "summary") L.summary = ev;
  if (ev.type === "error") S.error = ev.message;
  if (S.view === "processing") VIEWS.processing();
}

const CORE_TERMS = [["fee", "Fee"], ["usage_rights", "Usage rights"], ["exclusivity", "Exclusivity"], ["payment_terms", "Payment terms"], ["kill_fee", "Kill fee"]];
let readTimer = null;
function startReadTimer() {   // elapsed seconds + time-based bar while NDI reads (NDI returns all terms in one response)
  clearInterval(readTimer);
  readTimer = setInterval(() => {
    const L = S.live, st = (S.stages.reading || {}).status;
    if (!L || (st && st !== "running")) { clearInterval(readTimer); return; }
    const secs = Math.round((Date.now() - L.t0) / 1000), el = $("#elapsed"), bar = $("#rbar i");
    if (el) el.textContent = `${secs}s`;
    if (bar) bar.style.width = `${Math.min(92, (secs / 30) * 92)}%`;
  }, 500);
}

VIEWS.processing = () => {
  const L = S.live || {clauses: {}};
  const cl = Object.values(L.clauses);
  const rs = (S.stages.reading || {}).status || "running", reading = rs === "running";
  const secs = L.readSecs ?? Math.round((Date.now() - (L.t0 || Date.now())) / 1000);
  L.shown = L.shown || new Set();
  const isNew = k => !L.shown.has(k) && (L.shown.add(k), true);   // animate a chip only the first time it appears
  const sub = {
    reading: `${CORE_TERMS.map(([k, label]) => { const c = L.clauses[k];
        return c ? `<span class="chip got ${isNew("r" + k) ? "new" : ""}"><span class="dot ${c.status}"></span>${esc(label)}${c.page ? ` · p${c.page}` : ""}${ICON.check.replace("<svg", '<svg width="12" height="12"')}</span>`
                 : `<span class="chip wait">${esc(label)}</span>`; }).join("")}
      ${cl.filter(c => c.kind === "extra").map(c => `<span class="chip got ${isNew("r" + c.key) ? "new" : ""}">${esc(c.label)}${c.page ? ` · p${c.page}` : ""}</span>`).join("")}
      ${reading ? `<div class="readbar" id="rbar"><i style="width:${Math.min(92, (secs / 30) * 92)}%"></i></div><span class="faint readnote">Large or scanned PDFs take about 30 seconds</span>` : ""}`,
    rating: cl.filter(c => c.risk != null).map(c => `<span class="chip ${isNew("s" + c.key) ? "new" : ""}">${esc(c.label)} ${riskPill(c.risk)}</span>`).join(""),
    good: L.summary ? `<span class="chip"><span class="dot ambiguous"></span>${L.summary.watch.length} to watch</span><span class="chip"><span class="dot found"></span>${L.summary.good.length} look good</span>` : "",
  };
  const html = `
    <div class="head"><h1>Reading <span class="muted">${esc(L.name || "")}</span></h1></div>
    <ol class="steps">${STEPS.map(([k, label, who]) => {
      const st = S.stages[k] || {}, status = st.status || "pending";
      const cls = status === "running" ? "running" : status === "error" ? "done err" : status === "pending" ? "" : "done";
      const ic = status === "running" ? `<span class="spin"></span>` : status === "error" ? ICON.x : status === "pending" ? "" : ICON.check;
      const timer = k === "reading" ? ` <span class="faint">·</span> <span class="faint num" id="elapsed">${secs}s</span>` : "";
      return `<li class="step ${cls}"><span class="ic">${ic}</span><b>${label}${who ? ` <span class="faint">· ${who}</span>` : ""}${timer}</b>
        <em class="bd ${status === "pending" ? "waiting" : status}">${status === "pending" ? "Waiting" : ["live", "cached", "fallback", "error"].includes(status) ? status : ""}</em>
        <div class="sub">${sub[k] || ""}</div></li>`;
    }).join("")}</ol>
    ${L.extraction && L.extraction.cost_usd != null ? `<span class="tag" style="justify-self:start">NDI $${L.extraction.cost_usd.toFixed(3)}${L.extraction.reused ? " · reused" : ""}</span>` : ""}`;
  const sec = $("#view .proc");   // update in place: replacing the section would restart its fade-in on every event
  if (sec) sec.innerHTML = html; else $("#view").innerHTML = `<section class="proc" aria-live="polite">${html}</section>`;
};

function clauseRow(c, i) {
  const n = S.analysis && S.analysis.pages;
  const why = c.status === "not_found" ? `Not found in this contract${n ? ` (checked all ${n} page${n === 1 ? "" : "s"})` : ""}` : c.status === "ambiguous" ? "Unclear or conflicting" : "";
  const dist = c.risk_probabilities ? `<span class="dist" title="Drex risk distribution 1–5">${[1, 2, 3, 4, 5].map(n =>
    `<i style="height:${Math.max(2, (c.risk_probabilities[n] || 0) * 28)}px;background:rgba(${rk(n)},.7)"></i>`).join("")}</span>` : "";
  const amb = c.ambiguity_probabilities ? `<span>vague ${pct(c.ambiguity_probabilities.vague)}</span><span>conflicting ${pct(c.ambiguity_probabilities.conflict)}</span>` : "";
  return `<div class="row" style="animation-delay:${i * 50}ms" data-k="${esc(c.key)}">
    <button aria-expanded="false"><span class="dot ${c.status}"></span>
      <span><span class="lbl">${esc(c.label)}${c.kind === "extra" ? "<small>other</small>" : ""}${c.found_by ? `<span class="tag found-by">found by text search</span>` : ""}</span>${why ? `<br><span class="why">${why}</span>` : ""}</span>
      <span class="faint" style="font-size:12px">${c.page ? "p" + c.page : ""}</span>${riskPill(c.risk)}</button>
    <div class="detail"><div><div class="detail-in">
      ${c.quote ? `<blockquote>${esc(c.quote)}</blockquote>` : c.text ? `<blockquote>${esc(c.text)}</blockquote>` : `<blockquote class="none">No clause found for this term.</blockquote>`}
      <div class="kv">${c.page ? `<span class="tag">page ${c.page}</span>` : ""}${c.found_by ? `<span>found by searching the full text, confirmed by Drex</span>` : ""}<span>${STATUS[c.status]}</span>${amb}${dist}</div>
    </div></div></div></div>`;
}

VIEWS.overview = () => {
  const a = S.analysis;
  if (!a) return go("welcome");
  const by = Object.fromEntries(a.clauses.map(c => [c.key, c]));
  const watch = a.watch.map(k => by[k]), good = a.good.map(k => by[k]);
  const amb = a.clauses.filter(c => c.status === "ambiguous").length, miss = a.clauses.filter(c => c.status === "not_found").length;
  const ex = a.extraction || {};
  $("#view").innerHTML = `<section class="screen">
    ${pageHead("Overview", "The risks in this contract, worst first. Click a term to see the exact clause and page.")}
    <div class="ov">
      <div class="card">
        ${ringHTML(a.overall_risk)}
        <div class="counts"><span title="unclear"><span class="dot ambiguous"></span>${amb}</span><span title="missing"><span class="dot not_found"></span>${miss}</span><span title="clauses"><span class="dot found"></span>${a.clauses.length}</span></div>
        <div class="meta">
          ${a.parties && a.parties.brand_name ? `<div>Brand <b>${esc(a.parties.brand_name)}</b></div>` : ""}
          ${a.parties && a.parties.creator_name ? `<div>Creator <b>${esc(a.parties.creator_name)}</b></div>` : ""}
          <div>Read by <b>${ex.source === "ndi" ? "NDI" + (ex.ocr_applied ? " · OCR" : "") : esc(ex.source || "—")}</b></div>
          ${ex.cost_usd != null ? `<div>NDI cost <b>$${ex.cost_usd.toFixed(3)}${ex.reused ? " · reused" : ""}</b></div>` : ""}
          <div class="faint" style="justify-content:flex-start">${Object.values(a.stages).some(v => v === "cached") ? "Sample, pre-loaded" : "Read live"}</div>
        </div>
      </div>
      <div class="lists">
        <div class="list"><h2><span class="dot ambiguous"></span>Watch out</h2>
          ${watch.length ? watch.map(clauseRow).join("") : `<div class="empty">Nothing stands out.</div>`}</div>
        <div class="list"><h2><span class="dot found"></span>Looks good</h2>
          ${good.length ? good.map((c, i) => clauseRow(c, i + watch.length)).join("") : `<div class="empty">No low-risk terms found.</div>`}</div>
      </div>
    </div></section>`;
  animateRing($("#view"));
  $("#view").querySelectorAll(".row > button").forEach(b => b.addEventListener("click", () => {
    const row = b.parentElement, open = !row.classList.contains("open");
    row.classList.toggle("open", open); b.setAttribute("aria-expanded", open);
  }));
};
