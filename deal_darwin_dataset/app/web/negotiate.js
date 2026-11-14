/* Negotiate: evolutionary counter-offer search (Drex P(accept) x creator value), live chart + scrubber. */
const negUI = {persona: null, rate: "", brand: "", playbook: null, gen: null};

const CH = {W: 560, H: 200, P: {l: 36, r: 14, t: 12, b: 24}};
const chartMax = gens => Math.max(0.8, Math.ceil(Math.max(0, ...gens.map(g => g.best)) * 10) / 10);   // fixed unless exceeded
const cx = (i, N) => CH.P.l + i * (CH.W - CH.P.l - CH.P.r) / Math.max(1, N - 1);
const cy = (v, ymax) => CH.H - CH.P.b - v / ymax * (CH.H - CH.P.t - CH.P.b);
function chartSVG(gens, total, sel, ymax) {
  const {W, H, P} = CH, N = Math.max(total || 4, gens.length, 1);
  const seg = (k, cls) => gens.slice(1).map((g, i) => `<line class="${cls}" x1="${cx(i, N)}" y1="${cy(gens[i][k], ymax)}" x2="${cx(i + 1, N)}" y2="${cy(g[k], ymax)}"/>`).join("");
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Best fitness per generation" data-vw="${W}" data-l="${P.l}" data-r="${P.r}" data-nn="${N}">
    ${[0, ymax / 2, ymax].map(v => `<line class="ax" x1="${P.l}" x2="${W - P.r}" y1="${cy(v, ymax)}" y2="${cy(v, ymax)}"/><text x="${P.l - 6}" y="${cy(v, ymax) + 4}" text-anchor="end">${v.toFixed(2)}</text>`).join("")}
    ${Array.from({length: N}, (_, i) => `<text x="${cx(i, N)}" y="${H - 6}" text-anchor="middle">G${i}</text>`).join("")}
    <g id="segs">${seg("elite_mean", "mean")}${seg("best", "best")}</g>
    ${sel != null && gens[sel] ? `<line class="scrub" x1="${cx(sel, N)}" x2="${cx(sel, N)}" y1="${P.t}" y2="${H - P.b}"/>` : ""}
    <g id="pts">${gens.map((g, i) => `<circle class="pt ${i === sel ? "on" : ""}" cx="${cx(i, N)}" cy="${cy(g.best, ymax)}" r="${i === sel ? 6 : 4.5}"/>`).join("")}</g>
  </svg>`;
}

/* incremental updates while a search runs: at most one DOM write per 200 ms, never a full redraw */
let negTimer = null;
function scheduleNegPatch() { if (!negTimer) negTimer = setTimeout(() => { negTimer = null; negPatch(); }, 200); }
function negPatch() {
  const N = S.neg; if (!N || S.view !== "negotiate") return;
  const svg = document.querySelector("#chart svg"); if (!svg) return;
  if (chartMax(N.gens) !== N.ymax) { VIEWS.negotiate(); return; }   // scale grew (rare): one redraw
  const total = Math.max(N.total || 4, 1), done = N.gens.length, NS = "http://www.w3.org/2000/svg";
  for (let i = N.drawn || 0; i < done; i++) {
    const g = N.gens[i];
    if (i > 0) {
      const p = N.gens[i - 1];
      for (const [k, cls] of [["elite_mean", "mean"], ["best", "best"]]) {
        const ln = document.createElementNS(NS, "line");
        ln.setAttribute("class", cls + (cls === "best" ? " grow" : ""));
        [["x1", cx(i - 1, total)], ["y1", cy(p[k], N.ymax)], ["x2", cx(i, total)], ["y2", cy(g[k], N.ymax)]].forEach(([a, v]) => ln.setAttribute(a, v));
        svg.querySelector("#segs").appendChild(ln);
        if (cls === "best" && !reduced) { const L = Math.hypot(cx(i, total) - cx(i - 1, total), cy(g[k], N.ymax) - cy(p[k], N.ymax)); ln.style.strokeDasharray = L; ln.style.strokeDashoffset = L; ln.getBoundingClientRect(); ln.style.strokeDashoffset = 0; }
      }
    }
    const c = document.createElementNS(NS, "circle");
    c.setAttribute("class", "pt fadein"); c.setAttribute("cx", cx(i, total)); c.setAttribute("cy", cy(g.best, N.ymax)); c.setAttribute("r", 4.5);
    svg.querySelector("#pts").appendChild(c);
  }
  N.drawn = done;
  const g = N.gens[done - 1], prog = $("#negprog");
  if (prog) {
    prog.querySelector(".lbl").textContent = N.running ? `Generation ${Math.min(done + 1, total)} of ${total}` : `${total} generations`;
    prog.querySelector("i").style.width = `${(done / total) * 100}%`;
  }
  if (g) $("#gennow").innerHTML = `<b>G${g.gen}</b><span>${phrase(g.offer)}</span><span>fitness <b>${g.best.toFixed(3)}</b></span><span>P <b>${pct(g.p)}</b></span><span>+${g.new_calls} calls</span>`;
}

VIEWS.negotiate = () => {
  if (!S.analysis) return noContract("negotiate", "Negotiate", "See counter-offers the brand is likely to accept, ranked by chance of acceptance and value to you.", "See counter-offers the brand is likely to accept.");
  if (!S.meta) {  // config still loading
    $("#view").innerHTML = `<section class="screen">${pageHead("Negotiate", "See counter-offers the brand is likely to accept, ranked by chance of acceptance and value to you.")}<div class="ph" style="height:96px"></div><div class="ph" style="height:240px"></div></section>`;
    return setTimeout(() => S.view === "negotiate" && VIEWS.negotiate(), 400);
  }
  const m = S.meta || {personas: [], brands: {}, sample_personas: {}}, a = S.analysis, N = S.neg;
  if (!negUI.persona) negUI.persona = (a.sample && m.sample_personas[a.sample]) || "balanced";
  const running = N && N.running, gens = N ? N.gens : [], sel = negUI.gen ?? (gens.length ? gens.length - 1 : null);
  const g = sel != null ? gens[sel] : null;
  if (N) { N.ymax = chartMax(gens); N.drawn = gens.length; }
  const pb = N && N.plan ? N.plan.playbook : null;
  const rec = N && N.recovered;
  $("#view").innerHTML = `<section class="screen">
    ${pageHead("Negotiate", "See counter-offers the brand is likely to accept, ranked by chance of acceptance and value to you.", N && N.status ? `<em class="bd ${N.status}">${["live", "cached"].includes(N.status) ? N.status : ""}</em>` : "")}
    <div class="card"><div class="form">
      <label class="field">Persona<select id="persona">${m.personas.map(p => `<option value="${p}" ${p === negUI.persona ? "selected" : ""}>${p.replace(/_/g, " ")}</option>`).join("")}</select></label>
      <label class="field">My standard rate<input type="number" id="rate" min="1" step="50" placeholder="${a.sample ? "example default" : "optional"}" value="${esc(negUI.rate)}" style="width:150px"></label>
      <label class="field">Brand<select id="brand"><option value="">${a.brand ? "auto · " + esc(m.brands[a.brand] || a.brand) : "auto"}</option>${Object.entries(m.brands).map(([k, v]) => `<option value="${k}" ${k === negUI.brand ? "selected" : ""}>${esc(v)}</option>`).join("")}</select></label>
      <label class="file" tabindex="0"><input type="file" id="pb" accept="application/pdf,.pdf" hidden>${negUI.playbook ? esc(negUI.playbook.name) : "Brand playbook PDF (optional)"}</label>
      <span class="sp" style="flex:1"></span>
      <button class="btn" id="neggo" ${running ? "disabled" : ""}>${running ? "Searching…" : N ? "Run again" : "Find counter-offers"}</button>
    </div>
    ${pb ? `<div class="kv"><span>Playbook: <b style="color:var(--text)">${pb.source === "built-in" ? esc(pb.brand) + " (built-in)" : pb.source === "uploaded" ? "uploaded" : "generic default"}</b></span>${N.plan.rate ? `<span>Rate ${money(N.plan.rate)}</span>` : ""}<span>${N.plan.persona.replace(/_/g, " ")}</span></div>` : ""}
    ${N && N.error ? `<p class="err" style="margin:0">${esc(N.error)}</p>` : ""}</div>
    ${!N ? `<div class="empty">Pick a persona and run. Drex scores each offer against the brand playbook.</div>` : `
    <div class="neg">
      <div class="card"><h2>Top offers${rec ? ` <span class="tag ${rec.recovered > 0 ? "ok" : "bad"}" style="text-transform:none;letter-spacing:0" title="${rec.recovered.toFixed(3)} of ${rec.max.toFixed(3)} EV (simulated brand)">${rec.recovered > 0 ? `recovered ${pct(rec.recovered / rec.max)} of best possible` : "below as-written"}</span>` : ""}</h2>
        <div class="offers" role="radiogroup" aria-label="Offers">${N.offers ? N.offers.map((o, i) => `
          <button class="offer fade" role="radio" data-i="${i}" aria-checked="${i === S.offerSel}" style="animation-delay:${i * 60}ms">
            <span class="rank">${i + 1}</span><span class="phrase">${phrase(o)}${i === 0 ? ` <span class="tag accent" style="margin-left:6px">best</span>` : ""}</span>
            <span class="ometa"><span style="display:grid;grid-template-columns:auto 1fr;gap:8px;align-items:center">accept ${track(o.p)}</span>
              <span>P <b class="num">${pct(o.p)}</b></span><span>${o.fee_usd ? `<b class="num">${money(o.fee_usd)}</b> · ` : ""}value <b class="num">${o.utility.toFixed(2)}</b></span></span>
          </button>`).join("") : [0, 1, 2].map(() => `<div class="ph"></div>`).join("")}</div></div>
      <div class="card"><h2>Evolution ${N.n_calls ? `<span class="tag" style="text-transform:none;letter-spacing:0">${N.n_calls} Drex calls</span>` : ""}</h2>
        <div class="progress" id="negprog"><span class="lbl">${running ? `Generation ${Math.min(gens.length + 1, N.total || 4)} of ${N.total || 4}` : `${N.total || 4} generations`}</span><span class="pbar"><i style="width:${(gens.length / (N.total || 4)) * 100}%"></i></span></div>
        <div class="gen-now" id="gennow">${g ? `<b>G${g.gen}</b><span>${phrase(g.offer)}</span><span>fitness <b>${g.best.toFixed(3)}</b></span><span>P <b>${pct(g.p)}</b></span><span>+${g.new_calls} calls</span>` : `<span class="faint">Scoring the first 40 offers…</span>`}</div>
        <div class="chart" id="chart">${chartSVG(gens, N.total, running ? null : sel, N.ymax)}</div>
        <input type="range" id="gen" min="0" max="${Math.max(0, gens.length - 1)}" value="${sel ?? 0}" ${gens.length && !running ? "" : "disabled"} aria-label="Generation">
      </div>
    </div>`}
  </section>`;
  fill($("#view"));
  $("#persona").addEventListener("change", e => { negUI.persona = e.target.value; });
  $("#rate").addEventListener("input", e => { negUI.rate = e.target.value; });
  $("#brand").addEventListener("change", e => { negUI.brand = e.target.value; });
  $("#pb").addEventListener("change", e => { negUI.playbook = e.target.files[0] || null; VIEWS.negotiate(); });
  document.querySelector(".file").addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("#pb").click(); } });
  $("#neggo").addEventListener("click", runNegotiation);
  document.querySelectorAll(".offer").forEach(b => b.addEventListener("click", () => { S.offerSel = +b.dataset.i; VIEWS.negotiate(); }));
  const gi = $("#gen"); if (gi) gi.addEventListener("input", () => { negUI.gen = +gi.value; VIEWS.negotiate(); $("#gen").focus(); });
  const ch = $("#chart");
  if (ch && gens.length && !running) {
    let drag = false;
    const at = e => { const svg = ch.querySelector("svg"), r = svg.getBoundingClientRect(), W = +svg.dataset.vw, l = +svg.dataset.l, rr = +svg.dataset.r, NN = +svg.dataset.nn;
      const vx = (e.clientX - r.left) / r.width * W, i = Math.round((vx - l) / ((W - l - rr) / Math.max(1, NN - 1)));
      const k = Math.max(0, Math.min(gens.length - 1, i)); if (k !== sel) { negUI.gen = k; VIEWS.negotiate(); } };
    ch.addEventListener("pointerdown", e => { drag = true; at(e); });
    ch.addEventListener("pointermove", e => { if (drag) at(e); });
    window.addEventListener("pointerup", () => { drag = false; }, {once: true});
  }
};

async function runNegotiation() {
  const fd = new FormData();
  fd.append("job_id", S.analysis.jobId); fd.append("persona", negUI.persona || "");
  fd.append("rate", negUI.rate || ""); fd.append("brand", negUI.brand || "");
  if (negUI.playbook) fd.append("file", negUI.playbook, negUI.playbook.name);
  S.neg = {running: true, gens: [], offers: null, total: 4}; S.offerSel = 0; negUI.gen = null;
  sideBadge("negotiate", "");
  VIEWS.negotiate();
  const N = S.neg, rerender = () => { if (S.view === "negotiate") VIEWS.negotiate(); };
  try {
    const j = await api("/api/negotiate", fd);
    await stream(j.job_id, ev => {
      if (ev.type === "plan") { N.plan = ev; N.total = ev.generations; }
      if (ev.type === "stage") { if (ev.reset) N.gens = []; if (ev.status !== "running") { N.status = ev.status; sideBadge("negotiate", ev.status); } if (ev.error && ev.status === "error") N.error = ev.error; }
      if (ev.type === "gen") N.gens.push(ev.gen);
      if (ev.type === "offers") { N.offers = ev.offers; N.n_calls = ev.n_drex_calls; N.recovered = ev.recovered; }
      if (ev.type === "error") N.error = ev.message;
      if (ev.type === "plan" || ev.type === "offers" || (ev.type === "stage" && ev.status !== "running")) rerender();   // structural change
      else if (ev.type !== "done") scheduleNegPatch();                                              // incremental
    });
  } catch (e) { N.error = e.message; }
  N.running = false;
  if (!N.offers && !N.error) N.error = "The search didn't finish.";
  rerender();
}
