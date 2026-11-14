/* Creative studio: Drex Max checks images against the brand rules R1-R5; ask any yes/no question about an image. */
const RULE_SHORT = {R1: "Logo ≥22% width, clear space", R2: "Brand palette only", R3: "#ad ≥2.5% height, 4.5:1", R4: "No competitors", R5: "Copy above bottom 15%"};
const C = S.creative;   // {items: [{key, name, url, concept|image, score, status, error, asks}], sel, packSel}

function ensureConcepts() {
  if (C.items.length || !S.meta) return;
  C.items = S.meta.concepts.map((c, i) => ({key: c.name, name: `Concept ${i + 1}`, url: c.url, concept: c.name, asks: []}));
}

function tile(it) {
  const sc = it.score, pend = !sc;
  return `<div class="tile ${it.scoring ? "pending" : ""} ${C.sel === it.key ? "sel" : ""}">
    <button data-k="${esc(it.key)}" aria-label="${esc(it.name)}${sc ? `, fit ${sc.p_prod.toFixed(2)}` : ""}">
      <img src="${esc(it.url)}" alt="">${it.scoring ? `<span class="scan"></span>` : pend ? `<span class="nc">Not checked</span>` : ""}
      ${C.packSel === it.key ? `<span class="badge tag accent" style="background:var(--surface)">in export</span>` : ""}</button>
    <div class="fit"><span>${esc(it.name)}</span><b class="num">${sc ? sc.p_prod.toFixed(2) : it.scoring ? "…" : "—"}</b></div>
    <div class="rchips">${["R1", "R2", "R3", "R4", "R5"].map(r => sc ? `<span class="rc ${sc.prob[r] >= .5 ? "ok" : "no"}" title="${r} ${RULE_SHORT[r]} · p = ${sc.prob[r].toFixed(2)}">${r}</span>` : `<span class="rc pend">${r}</span>`).join("")}</div>
    ${it.error ? `<span class="err" style="font-size:12px">${esc(it.error)} <button class="link" data-retry="${esc(it.key)}">retry</button></span>` : sc && sc.status === "cached" ? `<em class="bd cached" style="justify-self:start">cached</em>` : ""}
  </div>`;
}

function inspector(it) {
  if (!it) return `<div class="empty">Pick an image to inspect it.</div>`;
  const sc = it.score;
  return `<div class="card inspect fade">
    <img src="${esc(it.url)}" alt="${esc(it.name)}">
    <div style="display:grid;gap:14px">
      <div class="head"><h1 style="font-size:20px">${esc(it.name)}</h1><span class="sp"></span>
        ${sc ? `<span class="tag ${sc.failed.length ? "bad" : "ok"}">${sc.failed.length ? "fails " + sc.failed.join(", ") : "passes all rules"}</span>` : ""}
        <button class="btn ghost sm" id="usepack" ${S.analysis ? "" : "disabled"}>${C.packSel === it.key ? "In export" : "Use in export"}</button></div>
      ${sc ? `<div style="display:grid;gap:8px">${Object.entries(sc.prob).map(([r, p]) => `<div class="opt"><span><b>${r}</b> <span class="muted">${RULE_SHORT[r]}</span></span>${track(p)}<span class="num">${p.toFixed(2)}</span></div>`).join("")}
          <div class="fit"><span>overall fit (product)</span><b class="num">${sc.p_prod.toFixed(3)}</b></div></div>`
        : `<div><button class="btn" id="checkone" ${it.scoring ? "disabled" : ""}>${it.scoring ? `<span class="spin"></span>Checking` : "Check rules"}</button></div>`}
      <div class="askbox">
        <div class="askrow"><input type="text" id="iq" placeholder="Ask about this image (yes / no)…" aria-label="Question about this image" style="flex:1">
          <button class="btn ghost" id="iqgo">Ask</button></div>
        ${it.asks.map(a => `<div class="big fade" style="grid-template-columns:1fr auto auto"><span>${esc(a.question)}</span>
          ${a.pending ? `<span class="spin"></span><span></span>` : a.error ? `<span class="err" style="font-size:12px">${esc(a.error)}</span><span></span>`
          : `<span class="num"><b>${pct(a.p)}</b></span><span class="tag ${a.label === "likely" ? "ok" : a.label === "unlikely" ? "bad" : "warn"}">${a.label}</span>`}</div>`).join("")}
      </div>
    </div></div>`;
}

VIEWS.creative = () => {
  ensureConcepts();
  const rules = S.meta ? S.meta.rules : {};
  const busy = C.items.some(i => i.scoring);
  $("#view").innerHTML = `<section class="screen">
    ${pageHead("Creative", "Check campaign visuals against the brand's rules. Images are made in Adobe Firefly; Drex Max scores them here.", `
      <a class="btn ghost sm" href="${(S.meta && S.meta.firefly) || "https://firefly.adobe.com"}" target="_blank" rel="noopener noreferrer">Open Firefly ↗</a>
      <button class="btn" id="checkall" ${busy || !C.items.length ? "disabled" : ""}>${busy ? `<span class="spin"></span>Checking` : "Check all"}</button>`)}
    <div class="rules">${Object.keys(rules).length ? Object.keys(rules).map(r => `<span class="rule" title="${esc(rules[r])}"><b>${r}</b>${RULE_SHORT[r] || ""}</span>`).join("") : `<span class="skel" style="width:320px;height:26px"></span>`}</div>
    <div class="gallery">${C.items.map(tile).join("")}
      <label class="addtile" id="addimg" tabindex="0"><input type="file" id="imgfile" accept="image/png,image/jpeg,image/webp" multiple hidden>${ICON.up.replace("<svg", '<svg width="26" height="26"')}<span>Add an image</span></label></div>
    ${inspector(C.items.find(i => i.key === C.sel))}
  </section>`;
  fill($("#view"));
  document.querySelectorAll(".tile > button").forEach(b => b.addEventListener("click", () => { C.sel = b.dataset.k; VIEWS.creative(); }));
  $("#imgfile").addEventListener("change", e => addImages([...e.target.files]));
  document.querySelectorAll("[data-retry]").forEach(b => b.addEventListener("click", () => { const t = C.items.find(i => i.key === b.dataset.retry); if (t) checkItem(t); }));
  $("#addimg").addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("#imgfile").click(); } });
  dropTarget($("#addimg"), addImages);
  $("#checkall").addEventListener("click", async () => { for (const it of C.items.filter(i => !i.score)) await checkItem(it); });
  const it = C.items.find(i => i.key === C.sel);
  if (it) {
    const one = $("#checkone"); if (one) one.addEventListener("click", () => checkItem(it));
    $("#usepack").addEventListener("click", () => { C.packSel = it.key; VIEWS.creative(); });
    const send = () => { const q = $("#iq").value.trim(); if (q) askImage(it, q); };
    $("#iqgo").addEventListener("click", send);
    $("#iq").addEventListener("keydown", e => { if (e.key === "Enter") send(); });
  }
  if (!S.meta) setTimeout(() => S.view === "creative" && VIEWS.creative(), 400);
};

const target = it => it.concept ? {concept: it.concept} : {image: it.image};
async function checkItem(it) {
  it.scoring = true; it.error = null; if (S.view === "creative") VIEWS.creative();
  try { it.score = await api("/api/creative/check", target(it)); sideBadge("creative", it.score.status === "cached" ? "cached" : ""); }
  catch (e) { it.error = e.message; }
  it.scoring = false; if (S.view === "creative") VIEWS.creative();
}
async function askImage(it, question) {
  const a = {question, pending: true}; it.asks.unshift(a); VIEWS.creative();
  try { Object.assign(a, await api("/api/creative/ask", {...target(it), question}), {pending: false}); }
  catch (e) { Object.assign(a, {pending: false, error: e.message}); }
  if (S.view === "creative") VIEWS.creative();
}
async function addImages(files) {
  for (const f of files) {
    const fd = new FormData(); fd.append("file", f, f.name);
    try {
      const r = await api("/api/image", fd);
      const it = {key: r.id, name: f.name.replace(/\.[^.]+$/, "").slice(0, 24), url: r.url, image: r.id, asks: []};
      C.items.push(it); C.sel = it.key; VIEWS.creative(); checkItem(it);
    } catch (e) { alertInline(e.message); }
  }
}
function alertInline(msg) {
  const p = document.createElement("p"); p.className = "err fade"; p.textContent = msg;
  $("#view .screen").prepend(p); setTimeout(() => p.remove(), 5000);
}
