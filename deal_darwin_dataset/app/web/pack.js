/* Pack: selected offer + risk summary + chosen image, printable. */
VIEWS.pack = () => {
  if (!S.analysis) return noContract("pack", "Export", "Get a one-page summary to send: your counter-offer, the risks, and the visual.", "Get a one-page summary to send.");
  const a = S.analysis, o = S.neg && S.neg.offers ? S.neg.offers[S.offerSel] : null;
  const img = S.creative.items.find(i => i.key === S.creative.packSel);
  const by = Object.fromEntries(a.clauses.map(c => [c.key, c]));
  const watch = a.watch.map(k => by[k]).slice(0, 4);
  $("#view").innerHTML = `<section class="screen">
    ${pageHead("Export", "Get a one-page summary to send: your counter-offer, the risks, and the visual.", `<button class="btn" id="export" ${o ? "" : "disabled"}>Export pack</button>`)}
    <div class="pack">
      <div class="card">
        <h2>Counter-offer</h2>
        ${o ? `<table>
          <tr><th>Fee</th><td>${pct(o.fee_mult)} of standard${o.fee_usd ? ` · ${money(o.fee_usd)}` : ""}</td></tr>
          <tr><th>Usage rights</th><td>${usage(o.usage_months)}</td></tr><tr><th>Exclusivity</th><td>${excl(o.excl_months)}</td></tr>
          <tr><th>Payment</th><td>net-${o.net_days}</td></tr><tr><th>Kill fee</th><td>${o.kill_pct}%</td></tr>
          <tr><th>Revisions</th><td>${o.revisions >= 99 ? "unlimited" : o.revisions}</td></tr>
          <tr><th>P(brand accepts)</th><td>${pct(o.p)}</td></tr></table>`
          : `<div class="empty">No offer picked yet. <button class="btn ghost sm" data-go="negotiate">Negotiate</button></div>`}
        <h2 style="margin-top:8px">Risk</h2>
        <div class="kv">${riskPill(a.overall_risk != null ? Math.round(a.overall_risk) : null)}<span>overall ${a.overall_risk != null ? a.overall_risk.toFixed(2) : "—"} / 5</span></div>
        ${watch.map(c => `<div class="kv"><span class="dot ${c.status}"></span><b style="color:var(--text)">${esc(c.label)}</b><span>${STATUS[c.status]}</span>${c.page ? `<span>p${c.page}</span>` : ""}${riskPill(c.risk)}</div>`).join("")}
      </div>
      <div class="card"><h2>Creative</h2>
        ${img ? `<img src="${esc(img.url)}" alt="${esc(img.name)}"><div class="fit"><span>${esc(img.name)}</span><b>${img.score ? img.score.p_prod.toFixed(2) : "—"}</b></div>`
          : `<div class="empty">No image picked. <button class="btn ghost sm" data-go="creative">Creative</button></div>`}</div>
    </div></section>`;
  document.querySelectorAll("[data-go]").forEach(b => b.addEventListener("click", () => go(b.dataset.go)));
  $("#export").addEventListener("click", () => exportPack(a, o, img, by));
};

function exportPack(a, o, img, by) {
  let sheet = $("#sheet");
  if (!sheet) { sheet = document.createElement("div"); sheet.id = "sheet"; document.body.appendChild(sheet); }
  const p = a.parties || {};
  sheet.innerHTML = `<h1>Deal Darwin pack · ${esc(displayName(a))}</h1>
    <div>${esc([p.brand_name, p.creator_name].filter(Boolean).join(" × "))}</div>
    <div class="cols"><div>
      <h2>Counter-offer</h2><table>
        <tr><th>Fee</th><td>${pct(o.fee_mult)} of standard${o.fee_usd ? ` (${money(o.fee_usd)})` : ""}</td></tr>
        <tr><th>Usage rights</th><td>${usage(o.usage_months)}</td></tr><tr><th>Exclusivity</th><td>${excl(o.excl_months)}</td></tr>
        <tr><th>Payment</th><td>net-${o.net_days}</td></tr><tr><th>Kill fee</th><td>${o.kill_pct}%</td></tr>
        <tr><th>Revisions</th><td>${o.revisions >= 99 ? "unlimited" : o.revisions}</td></tr><tr><th>P(brand accepts)</th><td>${pct(o.p)}</td></tr></table>
      <h2>Risk · overall ${a.overall_risk != null ? a.overall_risk.toFixed(2) : "—"} / 5</h2>
      <table>${a.clauses.map(c => `<tr><th>${esc(c.label)}</th><td>${STATUS[c.status]}</td><td>${c.risk != null ? "risk " + c.risk + "/5" : ""}</td><td>${c.page ? "p" + c.page : ""}</td></tr>`).join("")}</table>
      <h2>Cited clauses</h2>
      ${a.clauses.map(c => `<div><b>${esc(c.label)}</b>${c.quote ? `<q>${esc(c.quote)}</q>` : " — not found"}</div>`).join("")}
    </div><div>${img ? `<h2>Creative</h2><img src="${esc(img.url)}" alt=""><div>${img.score ? "fit " + img.score.p_prod.toFixed(3) : ""}</div>` : ""}</div></div>
    <p style="font-size:9px;color:#8A98A5;margin-top:16px">Drex answers with probabilities. Synthetic samples are measured against simulated brands.</p>`;
  const done = () => window.print();
  const im = sheet.querySelector("img");
  if (im && !im.complete) { im.onload = done; im.onerror = done; } else done();
}
