/* Evidence: read-only results from files on disk (GET /api/evidence). No model calls. */
let EV = null, EV_ERR = null;
const frac = ([a, b]) => `${a}/${b}`;
const sgn = x => (x > 0 ? "+" : "") + x.toFixed(3);

VIEWS.evidence = () => {
  if (!EV && !EV_ERR) {
    $("#view").innerHTML = `<section class="screen">${pageHead("Scorecard", "How well it works on our test set")}<div class="ev">${[1, 2, 3, 4].map(() => `<div class="skel" style="height:220px"></div>`).join("")}</div></section>`;
    api("/api/evidence").then(d => { EV = d; }).catch(e => { EV_ERR = e.message; }).finally(() => S.view === "evidence" && VIEWS.evidence());
    return;
  }
  if (EV_ERR) { $("#view").innerHTML = `<section class="screen">${pageHead("Scorecard", "How well it works on our test set")}<p class="err">${esc(EV_ERR)}</p></section>`; return; }
  const ex = EV.extraction || {rows: []}, ct = EV.counters || [], cr = EV.creative, cost = EV.cost || [];
  const cards = [];
  if (ex.rows.length) cards.push(`<div class="card wide"><h2>Contract extraction</h2>
    <table><tr><th>Variant</th><th>Status match</th><th></th><th>Risk ±1</th><th></th></tr>
    ${ex.rows.map(r => `<tr><td class="name">${esc(r.variant)} <span class="src">· ${r.source === "computed" ? "computed from cache" : "from console log"}</span></td>
      <td class="bar">${track(r.status[0] / r.status[1])}</td><td class="n">${frac(r.status)}</td>
      ${r.risk_within_1 ? `<td class="bar">${track(r.risk_within_1[0] / r.risk_within_1[1])}</td><td class="n">${frac(r.risk_within_1)}</td>` : `<td class="faint" colspan="2">—</td>`}</tr>`).join("")}</table>
    <p class="cap">Per-term status (found / unclear / missing) and risk 1–5 within one point, against hand-labelled answer keys: 4 example contracts × 5 terms; risk on the 19 terms the keys score.</p></div>`);
  if (ct.length) {
    const top = Math.max(...ct.map(r => r.max), ...ct.map(r => r.evolution), 0.01);
    cards.push(`<div class="card"><h2>Counter-offers · value recovered</h2>
      <div class="legend"><span><i style="background:var(--neutral);opacity:.6"></i>baseline (shortlist by creator value)</span><span><i style="background:var(--accent)"></i>Drex evolutionary search</span></div>
      <table><tr><th>Example</th><th colspan="2">Baseline</th><th colspan="2">Evolutionary</th><th>Max</th></tr>
      ${ct.map(r => `<tr><td class="ex">${esc((SAMPLES[r.contract] || {}).label || r.contract)}</td>
        <td class="bar">${track(Math.max(0, r.baseline) / top, "base")}</td><td class="n ${r.baseline < 0 ? "neg" : ""}">${sgn(r.baseline)}</td>
        <td class="bar">${track(Math.max(0, r.evolution) / top)}</td><td class="n ${r.evolution < 0 ? "neg" : ""}">${sgn(r.evolution)}</td>
        <td class="n muted">${sgn(r.max)}</td></tr>`).join("")}</table>
      <p class="cap">Value recovered = how much better than the contract as written; max = the best possible. Measured with the dataset's simulated brand; negative = worse than signing as written.</p></div>`);
  }
  if (cr) cards.push(`<div class="card"><h2>Creative rule check</h2>
    <table><tr><th>Rule</th><th></th><th>Correct</th></tr>
    ${Object.entries(cr.correct).map(([r, n]) => `<tr><td><b>${r}</b> <span class="muted">${esc((typeof RULE_SHORT !== "undefined" && RULE_SHORT[r]) || "")}</span></td>
      <td class="bar">${track(n / cr.n)}</td><td class="n">${n}/${cr.n}</td></tr>`).join("")}</table>
    <p class="cap">Drex Max yes/no per brand rule on ${cr.n} labelled ${esc(cr.split)} ads (pass if p ≥ ${cr.threshold}), compared with the ads' exact labels.</p></div>`);
  if (cost.length) cards.push(`<div class="card"><h2>Cost and calls</h2>
    <table>${cost.map(c => `<tr><td>${esc(c.label)}<br><span class="src">${Object.entries(c.detail).map(([k, v]) => `${k} ${c.unit === "usd" ? "$" + v.toFixed(3) : v}`).join(" · ")}</span></td>
      <td class="n"><span class="big-num">${c.unit === "usd" ? "$" + c.value.toFixed(3) : c.value}</span></td></tr>`).join("")}</table>
    <p class="cap">As recorded in the cache files: NDI cost of the last extraction run per contract, and Drex calls made by the last counter search per contract.</p></div>`);
  $("#view").innerHTML = `<section class="screen">
    ${pageHead("Scorecard", "How well it works on our test set")}
    ${cards.length ? `<div class="ev">${cards.join("")}</div>` : `<div class="empty">No results found in the cache files.</div>`}
    <p class="faint" style="font-size:12px;margin:0">Synthetic brands and contracts, small labeled sets. A pilot, not a benchmark.</p>
  </section>`;
  fill($("#view"));
};
