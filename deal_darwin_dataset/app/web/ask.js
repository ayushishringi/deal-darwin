/* Ask Drex: any question about the contract, answered as a probability. */
const EXAMPLES = ["Is the exclusivity too broad?", "Would a brand accept net-30?", "Does this contract let the brand cancel for free?"];
const askUI = {mode: "auto", draft: "", options: "", busy: false};

function detectOptions(q) {  // mirrors web_pipeline.detect_options for the hint
  const s = q.trim().replace(/\?+$/, "").trim(), parts = s.split(/\s+or\s+/i);
  if (parts.length < 2) return [];
  let head = parts[0]; const tail = head.includes(",") ? head.split(",").slice(1).map(x => x.trim()) : [];
  head = head.split(",")[0];
  const last = parts[parts.length - 1], k = Math.max(1, last.split(/\s+/).length);
  const opts = [head.split(/\s+/).slice(-k).join(" "), ...tail, ...parts.slice(1, -1), last].map(o => o.trim()).filter(Boolean);
  return [...new Set(opts)].slice(0, 6);
}

const likelihood = p => p >= 0.85 ? "Very likely" : p >= 0.65 ? "Likely" : p > 0.35 ? "Unsure" : p > 0.15 ? "Unlikely" : "Very unlikely";
const likeTone = p => p >= 0.65 ? "ok" : p > 0.35 ? "warn" : "bad";

function basedOn(ctx) {
  const by = Object.fromEntries((S.analysis ? S.analysis.clauses : []).map(c => [c.label, c]));
  const cards = ctx.map(c => {
    const full = by[c.label] || {}, q = full.quote || full.text;
    return `<div class="src-card"><div class="src-h"><span class="dot ${c.status}"></span><b>${esc(c.label)}</b>${c.page ? `<span class="muted">page ${c.page}</span>` : ""}</div>
      ${q ? `<p>${esc(q)}</p>` : `<p class="muted">Not in the contract.</p>`}</div>`;
  }).join("");
  return `<div class="based"><h3>Based on</h3>${cards || `<p class="muted">The full contract text.</p>`}</div>`;
}

function answerCard(a, i) {
  if (a.pending) return `<div class="card ans fade"><div class="q">${esc(a.question)}</div><div class="ph" style="height:40px"></div><span class="muted" style="font-size:14px">Asking Drex…</span></div>`;
  if (a.error) return `<div class="card ans fade"><div class="q">${esc(a.question)}</div><p class="err" style="margin:0">${esc(a.error)}</p>
    <div><button class="btn ghost sm" data-retry="${i}">Try again</button></div></div>`;
  let head, body = "";
  if (a.mode === "yesno") {
    head = `<div class="verdict ${likeTone(a.p)}"><span>${likelihood(a.p)}</span><b class="num">${pct(a.p)}</b></div>`;
    body = `<div class="big"><span class="track"><i data-w="${a.p * 100}%"></i></span><span class="faint" style="font-size:13px">chance the answer is yes</span></div>`;
  } else {
    const opts = Object.entries(a.probabilities).sort((x, y) => y[1] - x[1]);
    head = `<div class="verdict ok"><span>Most likely: ${esc(opts[0][0])}</span><b class="num">${pct(opts[0][1])}</b></div>`;
    body = opts.map(([o, p], j) => `<div class="opt ${j === 0 ? "first" : ""}"><span>${esc(o)}</span><span class="track"><i data-w="${p * 100}%"></i></span><span class="num">${pct(p)}</span></div>`).join("");
  }
  return `<div class="card ans fade"><div class="q">${esc(a.question)}</div>${head}${body}${basedOn(a.context || [])}
    <p class="faint" style="margin:0;font-size:13px">Drex gives probabilities, not explanations.</p></div>`;
}

VIEWS.ask = () => {
  if (!S.analysis) return noContract("ask", "Ask Drex", "Ask any yes/no question about your contract and get a probability.", "Ask any yes/no question about your contract and get a probability.");
  const detected = askUI.mode !== "yesno" ? detectOptions(askUI.draft) : [];
  const choice = askUI.mode === "choice" || (askUI.mode === "auto" && detected.length >= 2);
  $("#view").innerHTML = `<section class="screen">
    ${pageHead("Ask Drex", "Ask any yes/no question about your contract and get a probability.")}
    <div class="card askbox">
      <textarea id="q" placeholder="Ask anything about this contract…" aria-label="Your question">${esc(askUI.draft)}</textarea>
      <div class="askrow">
        <div class="seg" role="radiogroup" aria-label="Answer type">
          <button role="radio" data-m="yesno" aria-checked="${!choice}">yes / no</button>
          <button role="radio" data-m="choice" aria-checked="${choice}">pick one</button></div>
        <input type="text" id="opts" placeholder="options, comma separated" aria-label="Options" ${choice ? "" : "hidden"}
          value="${esc(askUI.options || detected.join(", "))}" style="flex:1;min-width:200px">
        <span class="sp" style="flex:1"></span>
        <button class="btn" id="askgo" ${askUI.busy ? "disabled" : ""}>Ask</button>
      </div>
      <div class="ex">${EXAMPLES.map(e => `<button data-ex="${esc(e)}">${esc(e)}</button>`).join("")}</div>
      <span class="faint" style="font-size:12px">Drex answers with probabilities.</span>
    </div>
    <div class="answers">${S.asks.length ? S.asks.map(answerCard).join("") : `<div class="empty">Your answers will appear here.</div>`}</div>
  </section>`;
  fill($("#view"));
  const q = $("#q");
  q.addEventListener("input", () => {
    askUI.draft = q.value;
    if (askUI.mode === "auto") {  // flip to pick-one when the question lists options
      const d = detectOptions(q.value), on = d.length >= 2;
      $("#opts").hidden = !on; if (on && !askUI.options) $("#opts").value = d.join(", ");
      document.querySelectorAll(".seg button").forEach(b => b.setAttribute("aria-checked", (b.dataset.m === "choice") === on));
    }
  });
  q.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submitAsk(); } });
  $("#opts").addEventListener("input", e => { askUI.options = e.target.value; });
  document.querySelectorAll(".seg button").forEach(b => b.addEventListener("click", () => {
    askUI.mode = b.dataset.m; askUI.options = ""; VIEWS.ask(); $("#q").focus();
  }));
  document.querySelectorAll(".ex button").forEach(b => b.addEventListener("click", () => {
    askUI.draft = b.dataset.ex; askUI.mode = "auto"; askUI.options = ""; submitAsk();
  }));
  $("#askgo").addEventListener("click", submitAsk);
  document.querySelectorAll("[data-retry]").forEach(b => b.addEventListener("click", () => {
    const a = S.asks[+b.dataset.retry]; S.asks.splice(+b.dataset.retry, 1); sendAsk(a.question, a.mode, a.options);
  }));
  if (!askUI.busy) q.focus();
};

function submitAsk() {
  const question = (askUI.draft || "").trim();
  if (!question || askUI.busy) return;
  const detected = askUI.mode !== "yesno" ? detectOptions(question) : [];
  const choice = askUI.mode === "choice" || (askUI.mode === "auto" && detected.length >= 2);
  const options = choice ? (askUI.options || detected.join(", ")).split(",").map(s => s.trim()).filter(Boolean) : [];
  askUI.draft = ""; askUI.options = "";
  sendAsk(question, choice ? "choice" : "yesno", options);
}

async function sendAsk(question, mode, options) {
  const entry = {question, mode, options, pending: true};
  S.asks.unshift(entry); askUI.busy = true;
  if (S.view === "ask") VIEWS.ask();
  try {
    Object.assign(entry, await api("/api/ask", {job_id: S.analysis.jobId, question, mode, options}), {pending: false});
  } catch (e) {
    Object.assign(entry, {pending: false, error: e.message});
  }
  askUI.busy = false;
  if (S.view === "ask") VIEWS.ask();
}
