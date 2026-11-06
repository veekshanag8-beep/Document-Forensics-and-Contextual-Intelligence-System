"use strict";
const $ = (s, r = document) => r.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const STATUS = {potential_manipulation: ["Potential manipulation", "pm"], inconsistency: ["Inconsistency", "inc"], observation: ["Observation", "obs"]};
const pill = (s) => `<span class="pill ${STATUS[s][1]}">${STATUS[s][0]}</span>`;
const DECISION = {confirmed: "Confirmed", dismissed: "Dismissed", needs_info: "Needs info"};

const S = {caseId: null, c: null, tab: "findings", sel: null, evIdx: 0, filter: "all", doc: null, layers: {fields: true, findings: true, units: false, ela: false}, hotField: null, poll: null};

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error((await r.text()) || r.statusText);
  return r.json();
}

/* ---------------------------------------------------------------- sidebar */
async function loadSamples() {
  const list = await api("/api/samples");
  $("#samples").innerHTML = list.map((s) => `<button data-s="${esc(s.name)}"><b>${esc(s.name.replace(/_/g, " "))}</b>
    <small>${esc(s.files.join(", "))}</small><small>${esc(s.description).slice(0, 150)}${s.description.length > 150 ? "…" : ""}</small></button>`).join("");
  $("#samples").onclick = async (e) => {
    const b = e.target.closest("button"); if (!b) return;
    const {case_id} = await api(`/api/cases/from-sample/${b.dataset.s}`, {method: "POST"});
    openCase(case_id); loadHistory();
  };
}
async function loadHistory() {
  const list = await api("/api/cases");
  $("#history").innerHTML = list.slice(0, 30).map((c) => `<div data-id="${c.id}"><span>${esc(c.name)}</span><span class="st">${esc(c.status)}</span></div>`).join("") || `<span class="muted">No investigations yet</span>`;
  $("#history").onclick = (e) => { const d = e.target.closest("div[data-id]"); if (d) openCase(d.dataset.id); };
  const a = await api("/api/audit?case_id=__none__");
  $("#chain").textContent = a.chain.valid ? `Audit chain valid · ${a.chain.entries} entries` : `AUDIT CHAIN BROKEN at #${a.chain.broken_at_seq}`;
  $("#chain").style.background = a.chain.valid ? "#ffffff22" : "#dc2626";
}
function setupUpload() {
  const inp = $("#files"), drop = $("#drop");
  const upd = () => { const n = inp.files.length; $("#dropText").textContent = n ? `${n} file(s): ${[...inp.files].map((f) => f.name).join(", ")}` : "Drop PDFs / scans here or click to choose"; $("#startBtn").disabled = !n; };
  inp.onchange = upd;
  ["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", (e) => { inp.files = e.dataTransfer.files; upd(); });
  $("#startBtn").onclick = async () => {
    const fd = new FormData();
    fd.append("name", $("#caseName").value || "Untitled investigation");
    [...inp.files].forEach((f) => fd.append("files", f));
    $("#startBtn").disabled = true;
    try { const {case_id} = await api("/api/cases", {method: "POST", body: fd}); openCase(case_id); loadHistory(); }
    catch (e) { alert("Upload failed: " + e.message); }
    inp.value = ""; upd();
  };
}

/* ---------------------------------------------------------------- case lifecycle */
async function openCase(id) {
  clearTimeout(S.poll);
  Object.assign(S, {caseId: id, sel: null, evIdx: 0, doc: null, tab: "findings", filter: "all", hotField: null});
  await refresh();
}
async function refresh() {
  const c = await api(`/api/cases/${S.caseId}`);
  S.c = c;
  if (c.status === "done") { renderResults(); loadHistory(); }
  else { renderProgress(c); if (c.status !== "failed") S.poll = setTimeout(refresh, 900); else loadHistory(); }
}
function renderProgress(c) {
  const pct = Math.round((c.progress || 0) * 100);
  $("#main").innerHTML = `<h2 style="margin:0">${esc(c.name)}</h2><div class="muted">Case ${esc(c.id)} · ${c.documents.length} document(s) · ${esc(c.status)}</div>
  <div class="stages">${c.stages.map((s, i) => `<div class="stage ${s.status}"><div class="s">Stage ${i + 1}</div><b>${esc(s.name)}</b>
     <div class="s">${s.status === "running" ? "running…" : s.status}${s.secs != null ? ` · ${s.secs}s` : ""}</div></div>`).join("")}</div>
  <div class="bar"><div style="width:${pct}%"></div></div><p class="muted">${pct}% · ${esc(c.stage)}</p>
  ${c.error ? `<p class="err">Investigation failed: ${esc(c.error)}</p>` : ""}
  <table class="tbl"><tr><th>ID</th><th>File</th><th>SHA-256 (recorded at submission)</th><th>Bytes</th></tr>
  ${c.documents.map((d) => `<tr><td>${d.doc_id}</td><td>${esc(d.filename)}</td><td style="font-family:monospace;font-size:11px">${d.sha256}</td><td>${d.size}</td></tr>`).join("")}</table>`;
}

/* ---------------------------------------------------------------- results */
const R = () => S.c.results;
const docById = (id) => R().documents.find((d) => d.doc_id === id);
const fileUrl = (kind, name) => `/api/cases/${S.caseId}/files/${kind}/${encodeURIComponent(name)}`;

function renderResults() {
  const r = R(), st = r.stats.by_status, pr = r.summary.review_priority;
  $("#main").innerHTML = `
  <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap"><h2 style="margin:0">${esc(r.case.name)}</h2>
    <span class="muted">Case ${esc(r.case.id)} · ${r.stats.documents} documents · ${r.stats.processing_seconds}s</span>
    <div class="actions"><button onclick="window.open('/api/cases/${S.caseId}/dossier','_blank')">Open dossier</button>
    <button onclick="location.href='/api/cases/${S.caseId}/dossier?download=1'">Download HTML</button>
    <button onclick="location.href='/api/cases/${S.caseId}/dossier.json'">Download JSON</button></div></div>
  <div class="summary" style="margin-top:10px">
    <div class="prio ${pr}"><span>Review priority</span><b>${pr.toUpperCase()}</b></div>
    <div class="kpi"><span class="pill pm">Potential manipulation</span><b>${st.potential_manipulation}</b></div>
    <div class="kpi"><span class="pill inc">Inconsistency</span><b>${st.inconsistency}</b></div>
    <div class="kpi"><span class="pill obs">Observation</span><b>${st.observation}</b></div>
    <div class="sumtext">${esc(r.summary.text)}<div class="muted" style="margin-top:6px;font-size:11.5px">${esc(r.summary.note)}</div></div>
  </div>
  <div class="tabs">${[["findings", `Findings (${r.findings.length})`], ["documents", "Documents & extraction"], ["cross", "Cross-document"], ["audit", "Audit trail"], ["caps", "Capabilities & limits"]]
    .map(([k, l]) => `<button data-t="${k}" class="${S.tab === k ? "on" : ""}">${l}</button>`).join("")}</div>
  <div id="tab"></div>`;
  $(".tabs").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; S.tab = b.dataset.t; renderResults(); };
  ({findings: tabFindings, documents: tabDocuments, cross: tabCross, audit: tabAudit, caps: tabCaps})[S.tab]();
}

/* ---------------------------------------------------------------- viewer */
function viewer(doc, page, opts = {}) {
  const p = doc.pages[page] || doc.pages[0];
  if (!p) return `<p class="muted">No page image (document could not be ingested).</p>`;
  const ela = opts.ela && doc.metadata?.forensic_maps?.ela;
  const src = ela ? fileUrl("evidence", doc.metadata.forensic_maps.ela) : fileUrl("pages", p.image);
  const W = p.width, H = p.height, parts = [];
  const rect = (b, cls, label, attrs = "") => {
    parts.push(`<rect class="box ${cls}" x="${b[0]}" y="${b[1]}" width="${Math.max(2, b[2] - b[0])}" height="${Math.max(2, b[3] - b[1])}" rx="3" ${attrs}></rect>`);
    if (label) parts.push(`<text class="boxlabel" x="${b[0]}" y="${Math.max(18, b[1] - 5)}" fill="currentColor">${esc(label)}</text>`);
  };
  if (opts.units) doc.units.filter((u) => u.page === p.index).forEach((u) => rect(u.bbox, u.hidden ? "hidden" : "unit", u.hidden ? "hidden text" : ""));
  if (opts.fields) Object.values(doc.fields).filter((f) => f.page === p.index).forEach((f) => rect(f.bbox, "field" + (opts.hotField === f.name ? " hot" : ""), ""));
  (opts.boxes || []).forEach((b) => rect(b.bbox, `${b.status}${b.hot ? " hot" : ""}`, b.label, `style="color:${b.status === "potential_manipulation" ? "#dc2626" : b.status === "inconsistency" ? "#b45309" : "#2563eb"}"`));
  return `<div class="viewer"><img src="${src}" alt="${esc(doc.filename)}"><svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">${parts.join("")}</svg></div>`;
}
function findingBoxes(doc, page, hotFinding, hotIdx) {
  const out = [];
  R().findings.forEach((f) => {
    if (f.category === "correlated" && (!hotFinding || f.id !== hotFinding.id)) return;
    f.evidence.forEach((e, i) => {
      if (e.doc_id !== doc.doc_id || !e.bbox || (e.page || 0) !== page) return;
      const hot = hotFinding && f.id === hotFinding.id;
      if (hotFinding && !hot && S.tab === "findings") return;
      out.push({bbox: e.bbox, status: f.status, label: f.id, hot: hot && (hotIdx == null || hotIdx === i)});
    });
  });
  return out;
}

/* ---------------------------------------------------------------- findings tab */
function tabFindings() {
  const r = R(), rv = S.c.reviews || {};
  const list = r.findings.filter((f) => S.filter === "all" || f.status === S.filter || (S.filter === "corroborated" && f.category === "correlated"));
  if (!S.sel && list.length) S.sel = list[0].id;
  const f = r.findings.find((x) => x.id === S.sel);
  $("#tab").innerHTML = `<div class="split"><div>
    <div class="filters">${[["all", "All"], ["potential_manipulation", "Potential manipulation"], ["inconsistency", "Inconsistency"], ["observation", "Observation"], ["corroborated", "Corroborated"]]
      .map(([k, l]) => `<button data-f="${k}" class="${S.filter === k ? "on" : ""}">${l}</button>`).join("")}</div>
    <div class="flist">${list.map((x) => `<div class="fcard ${x.status} ${x.id === S.sel ? "sel" : ""}" data-id="${x.id}">
      <div>${pill(x.status)} <span class="m">${x.id} · ${esc(x.category.replace("_", " "))} · conf ${x.confidence.toFixed(2)} · ${x.basis}</span></div>
      <div class="t">${esc(x.title)}</div>
      <div class="m">${esc([...new Set(x.evidence.map((e) => e.filename))].join(", "))}</div>
      ${rv[x.id] ? `<div class="rv">Reviewer: ${DECISION[rv[x.id].decision]}</div>` : ""}</div>`).join("") || `<p class="muted">No findings. All checks passed within their limits.</p>`}</div>
  </div><div id="detail">${f ? detailHtml(f) : ""}</div></div>`;
  $(".filters").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; S.filter = b.dataset.f; S.sel = null; S.evIdx = 0; tabFindings(); };
  $(".flist").onclick = (e) => { const d = e.target.closest(".fcard"); if (!d) return; S.sel = d.dataset.id; S.scroll = true; S.evIdx = firstBoxIdx(r.findings.find((x) => x.id === S.sel)); tabFindings(); };
  if (f) bindDetail(f);
}
const firstBoxIdx = (f) => Math.max(0, f.evidence.findIndex((e) => e.bbox));
function detailHtml(f) {
  const rv = (S.c.reviews || {})[f.id];
  const ev = f.evidence[S.evIdx] || f.evidence[0];
  const doc = ev ? docById(ev.doc_id) : null;
  return `<div class="detail">${pill(f.status)} <span class="muted">${f.id} · ${esc(f.category)} · check <code>${esc(f.check)}</code> · basis ${esc(f.basis)} · confidence ${f.confidence.toFixed(2)} · severity ${esc(f.severity)}</span>
    <h2>${esc(f.title)}</h2>
    <div class="expl">${esc(f.explanation)}</div>
    ${f.related.length ? `<p class="rel"><b>Related findings:</b> ${f.related.map((id) => `<a data-rel="${id}">${id}</a>`).join("")}</p>` : ""}
    <table class="evtable"><tr><th>Document</th><th>Field</th><th>Value</th><th>Location</th><th>Note</th></tr>
    ${f.evidence.map((e, i) => `<tr class="ev ${i === S.evIdx ? "sel" : ""}" data-i="${i}"><td>${esc(e.doc_id)} ${esc(e.filename)}</td><td>${esc(e.field || "")}</td><td>${esc(e.value || "")}</td>
      <td>${e.bbox ? `p${(e.page || 0) + 1} [${e.bbox.map((v) => Math.round(v)).join(", ")}]` : "document-level"}</td><td>${esc(e.note || "")}</td></tr>`).join("")}</table>
    <div class="crops">${f.evidence.filter((e) => e.crop).map((e) => `<img src="${fileUrl("evidence", e.crop)}" title="${esc(e.filename)}" data-i="${f.evidence.indexOf(e)}">`).join("")}</div>
    ${f.recommendation ? `<p><b>Further verification:</b> ${esc(f.recommendation)}</p>` : ""}
    <div class="review"><b>Reviewer decision:</b> ${rv ? `<span class="pill okp">${DECISION[rv.decision]}</span> <span class="muted">${esc(rv.reviewer)} · ${esc(rv.note)}</span>` : `<span class="muted">pending</span>`}
      <input id="rvNote" placeholder="Note (optional)"><button data-d="confirmed">Confirm</button><button data-d="dismissed">Dismiss</button><button data-d="needs_info">Needs info</button></div>
    ${doc ? `<div class="vhead"><b>Source:</b> ${esc(doc.doc_id)} · ${esc(doc.filename)} · page ${(ev.page || 0) + 1}
      <span class="muted">— box drawn at the recorded page coordinates</span></div>${viewer(doc, ev.page || 0, {boxes: findingBoxes(doc, ev.page || 0, f, S.evIdx)})}` : ""}
  </div>`;
}
function bindDetail(f) {
  const d = $("#detail");
  d.querySelectorAll("tr.ev, .crops img").forEach((el) => el.onclick = () => { S.evIdx = +el.dataset.i; S.scroll = true; $("#detail").innerHTML = detailHtml(f); bindDetail(f); });
  d.querySelectorAll("[data-rel]").forEach((a) => a.onclick = () => { S.filter = "all"; S.sel = a.dataset.rel; S.evIdx = firstBoxIdx(R().findings.find((x) => x.id === S.sel)); tabFindings(); });
  d.querySelectorAll("button[data-d]").forEach((b) => b.onclick = async () => {
    await api(`/api/cases/${S.caseId}/findings/${f.id}/review`, {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({decision: b.dataset.d, note: $("#rvNote").value, reviewer: "analyst"})});
    S.c.reviews = (await api(`/api/cases/${S.caseId}`)).reviews; tabFindings(); loadHistory();
  });
  const hot = d.querySelector(".box.hot");
  if (hot && S.scroll) setTimeout(() => hot.scrollIntoView({block: "center", behavior: "smooth"}), 60);
  S.scroll = false;
}

/* ---------------------------------------------------------------- documents tab */
function tabDocuments() {
  const docs = R().documents;
  if (!S.doc) S.doc = docs[0].doc_id;
  const d = docById(S.doc), md = d.metadata || {}, L = S.layers;
  const fields = Object.entries(d.fields || {});
  const sig = d.signature;
  const meta = md.pdf_metadata ? Object.entries(md.pdf_metadata).filter(([, v]) => v).map(([k, v]) => `${k}: ${v}`).join(" · ")
    : md.exif && Object.keys(md.exif).length ? Object.entries(md.exif).map(([k, v]) => `${k}: ${v}`).join(" · ") : "none";
  $("#tab").innerHTML = `<div class="doctabs">${docs.map((x) => `<button data-d="${x.doc_id}" class="${x.doc_id === S.doc ? "on" : ""}">${x.doc_id} · ${esc(x.filename)}</button>`).join("")}</div>
  <div class="docgrid"><div>
    <div class="layers"><b>Layers:</b>
      ${[["fields", "Extracted fields"], ["findings", "Findings"], ["units", "OCR / text units"], ["ela", "ELA heat-map"]].map(([k, l]) =>
        `<label><input type="checkbox" data-l="${k}" ${L[k] ? "checked" : ""} ${k === "ela" && !md.forensic_maps?.ela ? "disabled" : ""}> ${l}</label>`).join("")}</div>
    ${d.pages.length ? viewer(d, 0, {fields: L.fields, units: L.units, ela: L.ela, hotField: S.hotField, boxes: L.findings ? findingBoxes(d, 0, null) : []}) : `<p class="err">${esc(d.errors.join("; "))}</p>`}
  </div><div>
    <div class="docmeta"><b>${esc(d.doc_type_label)}</b> ${d.doc_type !== "unknown" ? `(classification confidence ${(d.doc_type_conf * 100).toFixed(0)}%)` : ""} · status <b>${esc(d.status)}</b><br>
      <span class="muted">Source: ${esc(md.source_format || d.media_type)} · text from ${esc(Object.values(md.text_source || {}).join(", ") || "-")} · SHA-256 ${esc(d.sha256.slice(0, 20))}…</span><br>
      <span class="muted">Type scores: ${Object.entries(d.doc_type_scores || {}).map(([k, v]) => `${k} ${v}`).join(" · ")}</span><br>
      <span class="muted">File metadata: ${esc(meta)}</span>
      ${md.structure ? `<br><span class="muted">Structure: ${md.structure.map((s) => esc(s.section)).join(" → ")}</span>` : ""}
      ${(md.missing_fields || []).length ? `<br><span class="err">Missing: ${esc(md.missing_fields.join(", "))}</span>` : ""}
      ${(md.hidden_text || []).length ? `<br><span class="err">Hidden text layer: ${md.hidden_text.map((h) => `'${esc(h.hidden)}' under '${esc(h.visible)}'`).join("; ")}</span>` : ""}
      ${d.errors.length ? `<br><span class="err">${esc(d.errors.join("; "))}</span>` : ""}
      ${sig ? `<br>Signature: ${sig.present ? "present" : "<span class='err'>not found</span>"} ${sig.crop ? `<img src="${fileUrl("evidence", sig.crop)}" style="height:34px;vertical-align:middle;border:1px solid #ddd">` : ""}` : ""}
    </div>
    ${fields.length ? `<table class="tbl"><tr><th>Field</th><th>Value as read</th><th>Normalised</th><th>Confidence</th><th>Source</th></tr>
      ${fields.map(([k, f]) => `<tr class="clk" data-f="${k}"><td>${esc(k)}</td><td>${esc(f.raw)}</td><td>${esc(f.value)}</td>
        <td><span class="conf"><i style="width:${f.conf * 100}%;background:${f.conf < 0.9 ? "#d97706" : ""}"></i></span>${f.conf.toFixed(2)}</td><td>${esc(f.source)}</td></tr>`).join("")}</table>` : `<p class="muted">No structured fields (unsupported or unreadable document).</p>`}
    ${(d.tables || []).map((t) => `<h4>Table: ${esc(t.name)} (${t.rows.length} rows)</h4><table class="tbl"><tr>${t.columns.map((c) => `<th>${esc(c)}</th>`).join("")}</tr>
      ${t.rows.map((row) => `<tr>${t.columns.map((c) => `<td>${esc(row.cells[c]?.text || "")}</td>`).join("")}</tr>`).join("")}</table>`).join("")}
  </div></div>`;
  $(".doctabs").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; S.doc = b.dataset.d; S.hotField = null; tabDocuments(); };
  document.querySelectorAll("[data-l]").forEach((c) => c.onchange = () => { S.layers[c.dataset.l] = c.checked; tabDocuments(); });
  document.querySelectorAll("tr[data-f]").forEach((tr) => tr.onclick = () => { S.hotField = tr.dataset.f; S.layers.fields = true; tabDocuments(); });
}

/* ---------------------------------------------------------------- cross-document tab */
function tabCross() {
  const r = R();
  $("#tab").innerHTML = `<div class="graph">${graphSvg(r.graph)}</div>
    <p class="muted">Documents (left) are linked to the entity values they assert (right). An attribute with more than one value node (red) is a conflict between documents. Arcs between documents show financial and signature cross-checks.</p>
    <h3>Comparison matrix</h3><table class="tbl"><tr><th>Attribute</th><th>Doc A</th><th>Value A</th><th>Doc B</th><th>Value B</th><th>Similarity</th><th>Result</th></tr>
    ${r.comparisons.map((c) => `<tr><td>${esc(c.attribute)}</td><td>${esc(c.doc_a)}</td><td>${esc(c.value_a)}</td><td>${esc(c.doc_b)}</td><td>${esc(c.value_b)}</td><td>${c.similarity}</td>
      <td class="${c.match ? "match" : c.match === false ? "conflict" : ""}">${c.match ? "match" : c.match === false ? "conflict" : "info"} <span class="muted">(${esc(c.relation)})</span></td></tr>`).join("")}</table>
    ${r.threads.length ? `<h3>Finding relationships</h3><table class="tbl"><tr><th>Linked findings</th><th>Documents</th><th>Fields</th></tr>${r.threads.map((t) => `<tr><td>${esc(t.findings.join(", "))}</td><td>${esc(t.documents.join(", "))}</td><td>${esc(t.fields.join(", "))}</td></tr>`).join("")}</table>` : ""}`;
}
function graphSvg(g) {
  const docs = g.nodes.filter((n) => n.type === "document"), ents = g.nodes.filter((n) => n.type === "entity");
  const W = 980, rowH = 30, H = Math.max(docs.length * 90, ents.length * rowH) + 60, pos = {};
  docs.forEach((n, i) => pos[n.id] = [190, 40 + (i + 0.5) * ((H - 60) / docs.length)]);
  ents.forEach((n, i) => pos[n.id] = [640, 40 + (i + 0.5) * ((H - 60) / ents.length)]);
  const lines = g.edges.map((e) => {
    const a = pos[e.source], b = pos[e.target]; if (!a || !b) return "";
    if (e.status === "asserts") {
      const conflict = ents.find((n) => n.id === e.target)?.conflict;
      return `<line x1="${a[0] + 80}" y1="${a[1]}" x2="${b[0]}" y2="${b[1]}" stroke="${conflict ? "#dc2626" : "#94a3b8"}" stroke-width="${conflict ? 2 : 1.2}" opacity=".8"/>`;
    }
    const col = e.status === "match" ? "#15803d" : e.status === "conflict" ? "#dc2626" : "#64748b", mx = 40 - Math.abs(a[1] - b[1]) * 0.25;
    return `<path d="M${a[0] - 80},${a[1]} C${mx},${a[1]} ${mx},${b[1]} ${b[0] - 80},${b[1]}" fill="none" stroke="${col}" stroke-width="2" stroke-dasharray="${e.status === "match" ? "" : "6 4"}"><title>${esc(e.label)}: ${e.status}</title></path>`;
  }).join("");
  const dn = docs.map((n) => { const [x, y] = pos[n.id]; return `<g><rect x="${x - 80}" y="${y - 20}" width="160" height="40" rx="8" fill="#1e3a5f"/><text x="${x}" y="${y - 3}" fill="#fff" font-size="12" text-anchor="middle" font-weight="600">${esc(n.label)}</text><text x="${x}" y="${y + 12}" fill="#c8d3e0" font-size="10.5" text-anchor="middle">${esc(n.doc_type.replace("_", " "))}</text></g>`; }).join("");
  const en = ents.map((n) => { const [x, y] = pos[n.id]; return `<g><rect x="${x}" y="${y - 12}" width="320" height="24" rx="12" fill="${n.conflict ? "#fde2e2" : "#f1f5f9"}" stroke="${n.conflict ? "#dc2626" : "#cbd5e1"}"/><text x="${x + 12}" y="${y + 4}" font-size="12" fill="${n.conflict ? "#a61b1b" : "#1f2933"}">${esc(n.label)}</text></g>`; }).join("");
  return `<svg viewBox="0 0 ${W} ${H}" width="100%">${lines}${dn}${en}</svg>`;
}

/* ---------------------------------------------------------------- audit + capabilities */
async function tabAudit() {
  const a = await api(`/api/audit?case_id=${S.caseId}`);
  $("#tab").innerHTML = `<p>Hash chain: <b class="${a.chain.valid ? "match" : "conflict"}">${a.chain.valid ? "VALID" : "BROKEN at #" + a.chain.broken_at_seq}</b> · ${a.chain.entries} entries in the global log. Each entry stores SHA-256(previous hash + entry), so any later edit is detectable.</p>
  <table class="tbl"><tr><th>#</th><th>Time (UTC)</th><th>Actor</th><th>Action</th><th>Details</th><th>Hash</th></tr>
  ${a.entries.map((e) => `<tr><td>${e.seq}</td><td>${esc(e.ts.slice(0, 23))}</td><td>${esc(e.actor)}</td><td>${esc(e.action)}</td>
    <td style="font-size:11.5px">${esc(Object.entries(e.details).filter(([k]) => k !== "findings" && k !== "trace").map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : v}`).join(", ")).slice(0, 260)}</td>
    <td style="font-family:monospace;font-size:10.5px">${e.hash.slice(0, 16)}</td></tr>`).join("")}</table>`;
}
function tabCaps() {
  const r = R();
  $("#tab").innerHTML = `<div class="docgrid"><div><h3>Capability status</h3><table class="tbl caps"><tr><th>Capability</th><th>Status</th></tr>
    ${r.capabilities.map((c) => `<tr><td>${esc(c.capability)}</td><td>${esc(c.status)}</td></tr>`).join("")}</table></div>
    <div><h3>Limitations &amp; assumptions</h3><ul>${r.limitations.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>
    <h3>Processing stages</h3><table class="tbl"><tr><th>Stage</th><th>Status</th><th>Seconds</th></tr>${r.stages.map((s) => `<tr><td>${esc(s.name)}</td><td>${esc(s.status)}</td><td>${s.secs ?? ""}</td></tr>`).join("")}</table>
    <h3>Evidence integrity</h3><table class="tbl"><tr><th>Document</th><th>Hash unchanged since submission</th></tr>${r.integrity.map((i) => `<tr><td>${esc(i.filename)}</td><td class="${i.unchanged ? "match" : "conflict"}">${i.unchanged ? "yes" : "NO"}</td></tr>`).join("")}</table></div></div>`;
}

setupUpload(); loadSamples(); loadHistory();
