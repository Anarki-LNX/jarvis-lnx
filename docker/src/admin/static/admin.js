/* JARVIS Verwaltung – Oberflaeche (ohne Framework). Alle Daten werden escaped eingesetzt (esc), CSP erlaubt nur 'self'. */
"use strict";
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const shell = $("#shell");
let current = null, refreshTimer = null, lastStatus = null;

/* ------------------------------------------------------------ Hilfen */
async function api(path, { method = "GET", body, raw = false } = {}) {
  const opt = { method, headers: { "X-JARVIS": "1" }, credentials: "same-origin" };
  if (body !== undefined) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
  const r = await fetch(path, opt);
  if (r.status === 401) { showLogin(); throw new Error("Bitte anmelden."); }
  if (raw) { if (!r.ok) throw new Error(`Fehler ${r.status}`); return r; }
  let d = null; try { d = await r.json(); } catch { /* leer */ }
  if (!r.ok) throw new Error((d && (typeof d.detail === "string" ? d.detail : JSON.stringify(d.detail))) || `Fehler ${r.status}`);
  return d;
}
function toast(msg, kind = "ok", ms = 4200) {
  const t = document.createElement("div"); t.className = "toast"; t.dataset.kind = kind; t.textContent = msg;
  $("#toasts").append(t); setTimeout(() => t.remove(), ms);
}
function setHTML(el, html) { el.innerHTML = html; $$("[data-w]", el).forEach((b) => { b.style.width = Math.max(0, Math.min(100, +b.dataset.w)) + "%"; }); return el; }
const fmtBytes = (n) => n == null ? "–" : n >= 1e9 ? (n / 1073741824).toFixed(1).replace(".", ",") + " GiB" : n >= 1e6 ? (n / 1048576).toFixed(0) + " MiB" : (n / 1024).toFixed(0) + " KiB";
const fmtDur = (s) => { s = Math.floor(s); const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60); return d ? `${d} T ${h} h` : h ? `${h} h ${m} min` : `${m} min`; };
const fmtTime = (iso) => { if (!iso) return "–"; const d = new Date(iso); return isNaN(d) ? String(iso) : d.toLocaleString("de-DE", { dateStyle: "short", timeStyle: "short" }); };
const busy = async (btn, fn) => { const t = btn.textContent; btn.disabled = true; btn.textContent = "…"; try { return await fn(); } catch (e) { toast(e.message, "err"); } finally { btn.disabled = false; btn.textContent = t; } };
const dot = (ok) => `<span class="dot" data-ok="${ok === true ? "true" : ok === false ? "false" : "warn"}"></span>`;
const sw = (name, on, extra = "") => `<label class="switch"><input type="checkbox" ${on ? "checked" : ""} data-sw="${esc(name)}" ${extra}><i></i></label>`;

const ICONS = {
  home: '<path d="M3 11l9-7 9 7"/><path d="M5 10v10h14V10"/>',
  brain: '<path d="M9 4a3 3 0 0 0-3 3v.5A3 3 0 0 0 4 13a3 3 0 0 0 2 5 3 3 0 0 0 6 0V5a1 1 0 0 0-3-1z"/><path d="M15 4a3 3 0 0 1 3 3v.5A3 3 0 0 1 20 13a3 3 0 0 1-2 5 3 3 0 0 1-6 0"/>',
  soul: '<circle cx="12" cy="8" r="4"/><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6"/>',
  mem: '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M8 9h8M8 13h8M8 17h5"/>',
  skill: '<path d="M13 3L4 14h7l-1 7 9-11h-7z"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  plug: '<path d="M9 2v6M15 2v6M6 8h12v3a6 6 0 0 1-12 0zM12 17v5"/>',
  shield: '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M9 12l2 2 4-4"/>',
  wave: '<path d="M3 12h2M7 8v8M11 5v14M15 8v8M19 11v2"/>',
  key: '<circle cx="8" cy="15" r="4"/><path d="M11 12l9-9M17 6l3 3M15 8l2 2"/>',
  phone: '<rect x="7" y="2" width="10" height="20" rx="2.5"/><path d="M11 18h2"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  log: '<path d="M4 6h16M4 10h16M4 14h10M4 18h7"/>',
  backup: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5M12 7v5l3 2"/>',
};
const ico = (n) => `<svg class="ico" viewBox="0 0 24 24" aria-hidden="true">${ICONS[n] || ""}</svg>`;

/* ------------------------------------------------------------ Aenderungsvorschau */
function diffHTML(diff) {
  return `<div class="diff">${diff.split("\n").map((l) => {
    const c = l.startsWith("+++") || l.startsWith("---") || l.startsWith("@@") ? "h" : l.startsWith("+") ? "a" : l.startsWith("-") ? "d" : "";
    return `<div class="${c}">${esc(l) || " "}</div>`;
  }).join("")}</div>`;
}
function openModal({ file = "", title, bodyHTML, buttons }) {
  $("#modalFile").textContent = file; $("#modalTitle").textContent = title;
  setHTML($("#modalBody"), bodyHTML);
  const foot = $("#modalFoot"); foot.innerHTML = "";
  for (const b of buttons) {
    const el = document.createElement("button"); el.type = "button"; el.className = "btn " + (b.cls || ""); el.textContent = b.label;
    el.addEventListener("click", () => b.onClick(el)); foot.append(el);
  }
  $("#modal").hidden = false; setTimeout(() => foot.lastChild?.focus(), 30);
}
const closeModal = () => { $("#modal").hidden = true; };
$("#modalX").addEventListener("click", closeModal);
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("#modal").hidden) closeModal(); });

function confirmBox(title, text, okLabel = "Ja, ausführen", danger = false) {
  return new Promise((res) => openModal({
    title, bodyHTML: `<p class="hint">${esc(text)}</p>`,
    buttons: [{ label: "Abbrechen", cls: "ghost", onClick: () => { closeModal(); res(false); } },
      { label: okLabel, cls: danger ? "danger" : "primary", onClick: () => { closeModal(); res(true); } }],
  }));
}

/** Startet eine Aenderung: req() liefert die Vorschau vom Server, dann Diff + Bestaetigung. */
async function change(req, onDone) {
  let pv;
  try { pv = await req(); } catch (e) { toast(e.message, "err"); return; }
  openModal({
    file: pv.file, title: pv.desc || "Änderung prüfen",
    bodyHTML: `${pv.danger ? `<div class="note danger">${esc(pv.danger)}</div>` : ""}
      <p class="hint">Vorschau der Änderung an <span class="mono">${esc(pv.path)}</span>. Vorher wird automatisch eine Sicherung angelegt, die du unter „Sicherungen“ wiederherstellen kannst.</p>
      ${diffHTML(pv.diff)}${pv.effect ? `<div class="note">${esc(pv.effect)}</div>` : ""}`,
    buttons: [
      { label: "Verwerfen", cls: "ghost", onClick: () => { api(`/api/change/${pv.preview}`, { method: "DELETE" }).catch(() => {}); closeModal(); } },
      { label: "Übernehmen", cls: pv.danger ? "danger" : "primary", onClick: (b) => busy(b, async () => {
        const r = await api(`/api/change/${pv.preview}/apply`, { method: "POST", body: {} });
        closeModal();
        if (r.check && !r.check.ok) {
          openModal({ file: pv.file, title: "Gespeichert – Prüfung meldet Probleme", bodyHTML:
            `<div class="note warn">„hermes config check“ hat Hinweise. Falls etwas nicht stimmt: Sicherungen → Wiederherstellen.</div><pre class="out">${esc(r.check.output)}</pre>`,
            buttons: [{ label: "Rückgängig machen", cls: "ghost", onClick: () => { closeModal(); change(() => api(`/api/backups/${r.backup}/restore`, { method: "POST", body: {} }), onDone); } },
              { label: "OK", cls: "primary", onClick: closeModal }] });
        } else toast("Gespeichert. Sicherung angelegt.");
        if (r.restart) needRestart(r.restart);
        onDone && onDone();
      }) },
    ],
  });
}
function needRestart(unit) {
  const b = $("#banner");
  setHTML(b, `<span>Einige Änderungen wirken erst nach einem Neustart des Hermes-Gateways (laufende Gespräche werden beendet).</span>
    <span class="inline"><button class="btn small ghost" data-later>Später</button><button class="btn small primary" data-now>Jetzt neu starten</button></span>`);
  b.hidden = false;
  $("[data-later]", b).onclick = () => { b.hidden = true; };
  $("[data-now]", b).onclick = (e) => busy(e.target, async () => { await restartUnit(unit, true); b.hidden = true; });
}
async function restartUnit(id, skipConfirm = false) {
  if (!skipConfirm && !await confirmBox("Dienst neu starten?", `Der Dienst wird kurz unterbrochen. ${id === "hermes" ? "Laufende Gespräche mit JARVIS werden abgebrochen." : ""}`, "Neu starten")) return;
  const r = await api(`/api/services/${id}/restart`, { method: "POST", body: {} });
  if (r.self) { toast("Verwaltung startet neu – Seite lädt gleich neu."); setTimeout(() => location.reload(), 5000); return; }
  if (r.ok) toast("Neu gestartet."); else toast(r.pending ? "Neustart läuft noch – Status unter Dienste." : "Neustart fehlgeschlagen.", r.pending ? "ok" : "err");
}

/* ------------------------------------------------------------ Bereiche */
const VIEWS = [
  { id: "uebersicht", group: "System", label: "Übersicht", icon: "home", title: "Übersicht", lead: "Zustand von Gehirn, Diensten und Handy auf einen Blick.", render: viewOverview },
  { id: "modell", group: "Gehirn", label: "Modell & Fallback", icon: "brain", title: "Modell & Fallback", lead: "Welches Sprachmodell JARVIS nutzt und worauf es ausweicht, wenn der PC aus ist.", render: viewModel },
  { id: "persona", group: "Gehirn", label: "Persönlichkeit", icon: "soul", title: "Persönlichkeit", lead: "Wer JARVIS ist und wie er spricht.", render: viewPersona },
  { id: "gedaechtnis", group: "Gehirn", label: "Gedächtnis", icon: "mem", title: "Gedächtnis", lead: "Was JARVIS sich dauerhaft merkt – über sich, die Umgebung und dich.", render: viewMemory },
  { id: "skills", group: "Fähigkeiten", label: "Skills", icon: "skill", title: "Skills", lead: "Anleitungen, die JARVIS bei Bedarf lädt. Aktivieren, deaktivieren, neue eintragen.", render: viewSkills },
  { id: "zeitplaene", group: "Fähigkeiten", label: "Zeitpläne", icon: "clock", title: "Zeitpläne", lead: "Aufgaben, die JARVIS regelmäßig selbst erledigt.", render: viewJobs },
  { id: "mcp", group: "Fähigkeiten", label: "MCP-Server", icon: "plug", title: "MCP-Server", lead: "Externe Werkzeuge, mit denen sich JARVIS verbindet.", render: viewMcp },
  { id: "regeln", group: "Sicherheit", label: "Bestätigungen", icon: "shield", title: "Bestätigungsregeln", lead: "Wann JARVIS vor gefährlichen Aktionen fragen muss.", render: viewApprovals },
  { id: "schluessel", group: "Sicherheit", label: "Schlüssel", icon: "key", title: "Schlüssel & Variablen", lead: "API-Schlüssel werden nie angezeigt – nur, ob sie gesetzt sind. Überschreiben ist jederzeit möglich.", render: viewEnv },
  { id: "sprache", group: "Geräte", label: "Sprache", icon: "wave", title: "Sprache", lead: "Stimme, Sprechtempo und Spracherkennung.", render: viewVoice },
  { id: "handy", group: "Geräte", label: "Handy", icon: "phone", title: "Handy", lead: "Zustand, Neustart, Kiosk.", render: viewPhone },
  { id: "dienste", group: "System", label: "Dienste", icon: "gear", title: "Dienste & Prüfungen", lead: "Dienste neu starten und Hermes-Selbsttests ausführen.", render: viewServices },
  { id: "protokolle", group: "System", label: "Protokolle", icon: "log", title: "Protokolle", lead: "Gefilterte Logs. Schlüssel werden automatisch unkenntlich gemacht.", render: viewLogs },
  { id: "sicherungen", group: "System", label: "Sicherungen", icon: "backup", title: "Sicherungen & Konto", lead: "Jede Änderung legt eine Sicherung an. Hier rückgängig machen, exportieren und das Passwort ändern.", render: viewBackups },
];

function buildNav() {
  let html = "", g = "";
  for (const v of VIEWS) {
    if (v.group !== g) { g = v.group; html += `<div class="nav-group">${esc(g)}</div>`; }
    html += `<button type="button" data-view="${v.id}">${ico(v.icon)}<span>${esc(v.label)}</span></button>`;
  }
  setHTML($("#nav"), html);
  $$("#nav button").forEach((b) => b.addEventListener("click", () => { location.hash = b.dataset.view; }));
}
let rendering = false;
// quiet = Hintergrund-Aktualisierung derselben Ansicht: kein „Lade …“, alte Ansicht bleibt bei Fehlern stehen.
async function show(id, quiet = false) {
  const v = VIEWS.find((x) => x.id === id) || VIEWS[0];
  if (quiet) {
    if (v.id !== current || rendering || !$("#modal").hidden) return;
    rendering = true; clearInterval(refreshTimer);
    try { await v.render($("#view")); } catch (e) { toast("Aktualisieren fehlgeschlagen: " + e.message, "err"); }
    finally { rendering = false; }
    return;
  }
  current = v.id; clearInterval(refreshTimer); closeModal();
  $$("#nav button").forEach((b) => { if (b.dataset.view === v.id) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current"); });
  $("#pageEyebrow").textContent = v.group; $("#pageTitle").textContent = v.title; $("#pageLead").textContent = v.lead;
  $("#pageActions").innerHTML = "";
  const view = $("#view"); setHTML(view, `<div class="panel span-12 empty">Lade …</div>`);
  document.title = `${v.title} · JARVIS Verwaltung`;
  rendering = true;
  try { await v.render(view); } catch (e) { setHTML(view, `<div class="panel span-12"><div class="note danger">${esc(e.message)}</div></div>`); } finally { rendering = false; }
}
window.addEventListener("hashchange", () => show(location.hash.slice(1)));
function actions(html) { setHTML($("#pageActions"), html); return $("#pageActions"); }

/* ------------------------------------------------------------ Orb + Statuschip */
function applyStatus(s) {
  lastStatus = s;
  const hermesOn = s.hermes.online, remote = s.mode === "remote", brainOn = remote || s.brain.online;
  const state = !hermesOn ? "error" : !brainOn ? (s.fallback.length ? "thinking" : "offline") : "idle";
  shell.dataset.state = state; window.Orb && Orb.set({ state });
  const chip = $("#chipBrain");
  chip.dataset.ok = !hermesOn ? "false" : brainOn ? "true" : "warn";
  chip.lastElementChild.textContent = !hermesOn ? "Hermes aus" : remote ? "Remote · Claude" : s.brain.online ? (s.mode === "local" ? "Lokal · online" : "Gehirn online") : s.fallback.length ? "PC aus · Claude" : "Gehirn offline";
}
async function pollStatus() { try { applyStatus(await api("/api/status")); } catch { /* Login o. Netz */ } }

/* ------------------------------------------------------------ Uebersicht */
async function viewOverview(view) {
  const s = await api("/api/status"); applyStatus(s);
  actions(`<button class="btn ghost" id="btnRefresh">Aktualisieren</button>`).querySelector("#btnRefresh").onclick = (e) => busy(e.target, () => show("uebersicht", true));
  const sys = s.system, memUsed = sys.mem_total - sys.mem_avail, diskUsed = sys.disk_total - sys.disk_free;
  const loaded = s.brain.loaded.map((m) => `<div class="row"><div class="grow"><div class="title mono">${esc(m.name)}</div>
      <div class="meta">VRAM ${fmtBytes(m.vram)} von ${fmtBytes(m.size)}${m.ctx ? ` · Kontext ${esc(m.ctx)}` : ""} · bleibt bis ${esc(fmtTime(m.until))}</div></div>
      <button class="btn small ghost" data-unload="${esc(m.name)}">Entladen</button></div>`).join("");
  const p = s.phone || {}, ps = p.status || {}, kw = s.phone ? "span-3" : "span-4";
  const phoneLine = !p.reachable ? "nicht erreichbar" : !p.configured ? "erreichbar · Steuerung nicht eingerichtet" : p.error ? esc(p.error) : `Akku ${esc(ps.akku_prozent ?? "?")} %${ps.laedt ? " · lädt" : ""}`;
  const units = s.units.map((u) => `<div class="row">${dot(u.active === "active" ? true : u.active === "activating" ? null : false)}
      <div class="grow"><div class="title">${esc(u.label)}</div><div class="meta mono">${esc(u.unit)} · ${esc(u.active)}/${esc(u.sub)}${u.memory ? " · " + fmtBytes(u.memory) : ""}</div></div>
      <button class="btn small ghost" data-restart="${esc(u.id)}">Neu starten</button></div>`).join("");
  setHTML(view, `
    <div class="panel ${kw} kpi"><span class="label">Gehirn · Modus <b>${esc({ local: "Lokal", auto: "Automatisch", remote: "Remote" }[s.mode] || "–")}</b></span><span class="value">${dot(s.mode === "remote" ? true : s.brain.online)}${s.mode === "remote" ? "Claude" : s.brain.online ? "PC online" : "PC offline"}</span>
      <span class="sub mono">${esc(s.model.default || "–")}</span><span class="sub">${s.brain.version ? "Ollama " + esc(s.brain.version) : esc(s.brain.url)}</span></div>
    <div class="panel ${kw} kpi"><span class="label">Hermes-Agent</span><span class="value">${dot(s.hermes.online)}${s.hermes.online ? "Bereit" : "Aus"}</span>
      <span class="sub">Bestätigungen: <b>${esc({ manual: "immer fragen", smart: "smart", off: "AUS" }[s.approvals] || s.approvals || "–")}</b></span>
      <span class="sub">Fallback: ${s.fallback.length ? s.fallback.map((f) => esc(f.model)).join(", ") : "keiner"}</span></div>
    <div class="panel ${kw} kpi"><span class="label">Sprache</span><span class="value">${dot(s.stt.online && s.ui.online)}${s.stt.online && s.ui.online ? "Bereit" : "Gestört"}</span>
      <span class="sub">Erkennung ${s.stt.online ? "ok" : "aus"} · Oberfläche ${s.ui.online ? "ok" : "aus"}</span></div>
    ${s.phone ? `<div class="panel span-3 kpi"><span class="label">Handy</span><span class="value">${dot(p.reachable && !p.error ? true : p.reachable ? null : false)}${p.reachable ? "Im WLAN" : "Offline"}</span>
      <span class="sub">${phoneLine}</span>${ps.wlan_signal_dbm != null ? `<span class="sub">WLAN ${esc(ps.wlan_ssid || "")} ${esc(ps.wlan_signal_dbm)} dBm</span>` : ""}</div>` : ""}

    <div class="panel span-7"><div class="panel-head"><h3>Geladene Modelle (VRAM auf dem PC)</h3>${s.gpu_label ? `<span class="tag">${esc(s.gpu_label)}</span>` : ""}</div>
      <div class="rows">${loaded || `<div class="empty">${s.brain.online ? "Kein Modell geladen – die erste Frage lädt es (~4 s)." : "PC/Ollama nicht erreichbar."}</div>`}</div>
      <p class="hint small">Tipp: Für Spiele am PC das Modell entladen; JARVIS lädt es bei der nächsten Frage selbst wieder.</p></div>
    <div class="panel span-5"><h3>Container jarvis</h3>
      <div class="kpi"><span class="label">Arbeitsspeicher ${fmtBytes(memUsed)} / ${fmtBytes(sys.mem_total)}</span><div class="bar"><i data-w="${memUsed / sys.mem_total * 100}"></i></div></div><br>
      <div class="kpi"><span class="label">Speicher ${fmtBytes(diskUsed)} / ${fmtBytes(sys.disk_total)}</span><div class="bar" ${diskUsed / sys.disk_total > .85 ? "data-warn" : ""}><i data-w="${diskUsed / sys.disk_total * 100}"></i></div></div><br>
      <div class="sub muted">Last ${esc(sys.load.join(" · "))} (${sys.cpus} Kerne) · läuft seit ${fmtDur(sys.uptime)}</div></div>
    <div class="panel span-12"><div class="panel-head"><h3>Dienste</h3><a href="#dienste" class="small">Prüfungen →</a></div><div class="rows">${units}</div></div>`);
  $$("[data-restart]", view).forEach((b) => b.onclick = () => busy(b, () => restartUnit(b.dataset.restart).then(() => show("uebersicht", true))));
  $$("[data-unload]", view).forEach((b) => b.onclick = () => busy(b, async () => { await api("/api/models/unload", { method: "POST", body: { name: b.dataset.unload } }); toast("Modell entladen."); show("uebersicht", true); }));
  clearInterval(refreshTimer);
  refreshTimer = setInterval(() => { if (current === "uebersicht" && !document.hidden) show("uebersicht", true); }, 20000);
}

/* ------------------------------------------------------------ Gehirn & Modell */
const usd = (n) => "$" + n.toFixed(2).replace(".", ",");
async function viewModel(view) {
  const [m, br] = await Promise.all([api("/api/models"), api("/api/brain")]);
  const cur = br.local_model || m.model.default || "";
  const opts = [...new Set([cur, ...m.ollama].filter(Boolean))].map((n) => `<option ${n === cur ? "selected" : ""} value="${esc(n)}">${esc(n)}${m.sizes[n] ? ` (${fmtBytes(m.sizes[n])})` : ""}</option>`).join("");
  const modes = [
    ["local", "Lokal", "Nur Gemma auf deinem PC. Keine Cloud. Ist der PC aus, meldet JARVIS „Gehirn offline“."],
    ["auto", "Automatisch", "Zuerst Gemma auf dem PC; antwortet der nicht, übernimmt Claude."],
    ["remote", "Remote", "Nur Claude. Der PC und seine Grafikkarte werden geschont."]];
  const claudeCards = (name, sel) => Object.entries(br.models).map(([id, c]) => `<label class="choice small-choice">
      <input type="radio" name="${name}" value="${id}" ${id === sel ? "checked" : ""}><span class="c-title">${esc(c.name)}</span>
      <span class="c-sub">${usd(c.in)} Eingabe / ${usd(c.out)} Ausgabe pro Mio. Token</span><span class="c-sub muted">${esc(c.hint)}</span></label>`).join("");
  setHTML(view, `
    <div class="panel span-12"><div class="panel-head"><h3>Gehirn-Modus</h3><span class="tag cyan">aktiv: ${esc(br.label)} · ${esc(br.models[br.active_model]?.name || br.active_model || "")}${br.mode === "auto" ? " (Ausweich: " + esc(br.models[br.fallback_model]?.name || "") + ")" : ""}</span></div>
      <div class="choices">${modes.map(([v, t, h]) => `<label class="choice"><input type="radio" name="bmode" value="${v}" ${br.mode === v ? "checked" : ""}>
        <span class="c-title">${t}${br.mode === v ? ' <span class="tag cyan">aktiv</span>' : ""}</span><span class="c-sub">${h}</span></label>`).join("")}</div>
      <div id="pickRemote"><h3 class="mt">Remote-Hauptmodell <span class="muted small">(antwortet bei Remote auf alles)</span></h3>
        <div class="choices">${claudeCards("bremote", br.remote_model)}</div></div>
      <div id="pickFallback"><h3 class="mt">Ausweich-Modell <span class="muted small">(bei Automatisch, wenn der PC nicht antwortet)</span></h3>
        <div class="choices">${claudeCards("bfallback", br.fallback_model)}</div></div>
      <div class="note warn mt" id="privacyNote">Datenschutz: Bei Remote und beim Ausweichen auf Claude gehen die Gesprächstexte an Anthropic (USA). Audio, Spracherkennung und Sprachausgabe bleiben lokal.</div>
      <p class="hint small mt">Umschalten wirkt ab der nächsten Frage, ohne Neustart und ohne PC-Last. Auch am Handy umschaltbar (Einstellungen oder Sprachbefehl).</p>
      <div class="inline mt"><span class="muted small">Anthropic-Schlüssel: <b>${esc(br.anthropic_key || "nicht gesetzt")}</b></span><span class="grow"></span>
        <button class="btn ghost small" id="fbCheck">Prüfen</button><button class="btn ghost small" id="fbLive" title="Eine Mini-Anfrage an Claude">Live prüfen (&lt; 0,1 Cent)</button>
        <button class="btn primary" id="brainSave">Übernehmen …</button></div>
      <pre class="out mt" id="fbOut" hidden></pre></div>
    <div class="panel span-7"><h3>Lokales Modell (PC-Ollama)</h3>
      ${br.mode === "remote" ? `<div class="note">Im Modus Remote ruht das lokale Modell. Diese Auswahl gilt wieder, sobald du auf Lokal oder Automatisch stellst.</div><br>` : ""}
      <label class="field"><span>Modell auf dem PC (Ollama ${m.online ? "erreichbar" : "nicht erreichbar"})</span><select id="mDefault" ${br.mode === "remote" ? "disabled" : ""}>${opts}</select></label>
      <div class="grid2">
        <label class="field"><span>Kontextlänge (Token)</span><input id="mCtx" type="number" min="2048" step="1024" value="${esc(m.model.context_length || "")}"><small>64k = 65536. Mehr Kontext braucht mehr VRAM.</small></label>
        <label class="field"><span>Denktiefe (global)</span><select id="mReason">${["none", "low", "medium", "high"].map((r) => `<option ${r === m.reasoning ? "selected" : ""} value="${r}">${{ none: "aus", low: "niedrig", medium: "mittel", high: "hoch" }[r]}</option>`).join("")}</select>
          <small>Sprachfragen vom Handy denken immer ohne – das hält die Antwort schnell.</small></label></div>
      <div class="note warn">Modelle, die nicht in den Grafikspeicher passen, machen den PC träge. Gemma 4 26B mit 64k belegt ~12,9 GiB.</div><br>
      <button class="btn primary" id="saveModel">Speichern …</button></div>
    <div class="panel span-5"><h3>Projekt-Claude</h3>
      <p class="hint">Claude Code für Programmier-Aufträge („Jarvis, frag Claude …“). Kosten fallen nur bei Nutzung an.</p>
      ${br.projekt ? `<div class="choices one">${claudeCards("pclaude", br.projekt)}</div><br><button class="btn primary" id="pcSave">Übernehmen …</button>` : `<div class="note">Projekt-Claude ist nicht eingerichtet.</div>`}</div>`);
  const upd = () => { const md = $("input[name=bmode]:checked", view)?.value; $("#pickRemote").hidden = md !== "remote"; $("#pickFallback").hidden = md !== "auto"; $("#privacyNote").hidden = md === "local"; };
  $$("input[name=bmode]", view).forEach((r) => r.onchange = upd); upd();
  $("#brainSave").onclick = () => change(() => api("/api/brain/save", { method: "POST", body: { mode: $("input[name=bmode]:checked", view).value, remote_model: $("input[name=bremote]:checked", view)?.value, fallback_model: $("input[name=bfallback]:checked", view)?.value } }), () => { show("modell"); pollStatus(); });
  $("#saveModel").onclick = () => change(() => api("/api/models/save", { method: "POST", body: { ...(br.mode === "remote" ? {} : { default: $("#mDefault").value }), context_length: $("#mCtx").value ? +$("#mCtx").value : null, reasoning: $("#mReason").value } }), () => show("modell"));
  if ($("#pcSave")) $("#pcSave").onclick = () => change(() => api("/api/brain/projekt", { method: "POST", body: { model: $("input[name=pclaude]:checked", view).value } }), () => show("modell"));
  const check = (live) => (e) => busy(e.target, async () => { const o = $("#fbOut"); o.hidden = false; o.textContent = "Prüfe …"; const r = await api("/api/models/check", { method: "POST", body: { live } }); o.textContent = (r.ok ? "✓ Nutzbar\n\n" : "✗ Probleme gefunden\n\n") + r.output; });
  $("#fbCheck").onclick = check(false); $("#fbLive").onclick = check(true);
}

/* ------------------------------------------------------------ Persoenlichkeit */
async function viewPersona(view) {
  const p = await api("/api/persona");
  setHTML(view, `
    <div class="panel span-7"><div class="panel-head"><h3>SOUL.md – Identität von Hermes/JARVIS</h3><span class="counter" id="soulCount"></span></div>
      <p class="hint">Steht an erster Stelle im System-Prompt und gilt überall (Handy, Zeitpläne, Chat).</p>
      <textarea id="soul" class="mono" rows="18" spellcheck="true">${esc(p.soul)}</textarea><br><br>
      <button class="btn primary" id="saveSoul">Speichern …</button></div>
    <div class="panel span-5"><h3>Sprach-Persona am Handy</h3>
      <p class="hint">Zusätzliche Anweisungen nur für Sprachgespräche über das Handy (kurz, gesprochen, ohne Markdown). Leer lassen = Standard der Oberfläche.</p>
      ${p.ui_supported ? "" : `<div class="note warn">Die Handy-Oberfläche liest diese Einstellung noch nicht (Datei ui.json fehlt). Sie wird beim Speichern angelegt.</div><br>`}
      <textarea id="uiPersona" rows="12">${esc(p.ui_persona || "")}</textarea><br><br>
      <button class="btn primary" id="saveUiPersona">Speichern …</button>
      <div class="note small">Jede Änderung an der Persönlichkeit macht die erste Antwort danach einmalig ~8 s langsamer (Prompt-Cache).</div></div>`);
  const cnt = () => { $("#soulCount").textContent = `${$("#soul").value.length} Zeichen`; };
  $("#soul").addEventListener("input", cnt); cnt();
  $("#saveSoul").onclick = () => change(() => api("/api/persona/save", { method: "POST", body: { soul: $("#soul").value } }), () => show("persona"));
  $("#saveUiPersona").onclick = () => change(() => api("/api/persona/save", { method: "POST", body: { ui_persona: $("#uiPersona").value } }), () => show("persona"));
}

/* ------------------------------------------------------------ Gedaechtnis */
async function viewMemory(view) {
  const m = await api("/api/memory");
  const block = (key, title, hint) => `<div class="panel span-6"><div class="panel-head"><h3>${title}</h3><span class="counter" id="cnt-${key}"></span></div>
      <p class="hint">${hint}${m.enabled[key] ? "" : " <b>(in der Konfiguration abgeschaltet)</b>"}</p>
      <div class="list-edit" id="list-${key}">${m[key].map((e) => memItem(e)).join("")}</div><br>
      <div class="inline"><button class="btn ghost small" data-add="${key}">+ Eintrag</button><span class="grow"></span><button class="btn primary small" data-save="${key}">Speichern …</button></div></div>`;
  const memItem = (t = "") => `<div class="item"><textarea rows="2">${esc(t)}</textarea><button class="icon-btn" data-del title="Entfernen">✕</button></div>`;
  setHTML(view, block("memory", "Notizen von JARVIS (MEMORY.md)", "Fakten zur Umgebung, Abläufe, Gelerntes.") + block("user", "Über dich (USER.md)", "Vorlieben, Gewohnheiten, wie du angesprochen werden willst."));
  for (const key of ["memory", "user"]) {
    const list = $(`#list-${key}`), lim = m.limits[key];
    const upd = () => { const n = $$("textarea", list).reduce((a, t) => a + t.value.trim().length, 0) + Math.max(0, $$("textarea", list).length - 1) * 3; const c = $(`#cnt-${key}`); c.textContent = `${n} / ${lim} Zeichen`; c.toggleAttribute("data-over", n > lim); };
    const wire = () => { $$("[data-del]", list).forEach((b) => b.onclick = () => { b.parentNode.remove(); upd(); }); $$("textarea", list).forEach((t) => t.oninput = upd); upd(); };
    wire();
    $(`[data-add=${key}]`).onclick = () => { list.insertAdjacentHTML("beforeend", memItem()); wire(); $$("textarea", list).pop().focus(); };
    $(`[data-save=${key}]`).onclick = () => change(() => api("/api/memory/save", { method: "POST", body: { which: key, entries: $$("textarea", list).map((t) => t.value) } }), () => show("gedaechtnis"));
  }
}

/* ------------------------------------------------------------ Skills */
let skillFilter = { q: "", cat: "", only: "" };
async function viewSkills(view) {
  const d = await api("/api/skills");
  actions(`<button class="btn primary" id="newSkill">+ Neuer Skill</button>`).querySelector("#newSkill").onclick = () => skillEditor(null, d.categories);
  const on = d.items.filter((s) => s.enabled).length;
  setHTML(view, `<div class="panel span-12">
      <div class="toolbar"><input id="sq" placeholder="Suchen …" value="${esc(skillFilter.q)}">
        <select id="scat"><option value="">Alle Kategorien</option>${d.categories.map((c) => `<option ${c === skillFilter.cat ? "selected" : ""}>${esc(c)}</option>`).join("")}</select>
        <select id="sonly"><option value="">Alle</option><option value="on">Nur aktive</option><option value="off">Nur deaktivierte</option><option value="own">Nur eigene</option></select>
        <span class="grow"></span><span class="tag cyan">${on} von ${d.items.length} aktiv</span></div>
      <div class="skill-grid" id="sgrid"></div></div>`);
  $("#sonly").value = skillFilter.only;
  const draw = () => {
    const q = skillFilter.q.toLowerCase();
    const items = d.items.filter((s) => (!skillFilter.cat || s.category === skillFilter.cat) && (!q || (s.name + s.description + s.tags.join(" ")).toLowerCase().includes(q))
      && (!skillFilter.only || (skillFilter.only === "on" ? s.enabled : skillFilter.only === "off" ? !s.enabled : s.own)));
    setHTML($("#sgrid"), items.map((s) => `<div class="skill" ${s.enabled ? "" : "data-off"}>
        <div class="top"><div class="grow"><div class="name">${esc(s.name)}</div><div class="meta muted small">${esc(s.category || "–")}${s.version ? " · v" + esc(s.version) : ""}</div></div>${sw("skill:" + s.name, s.enabled, `data-name="${esc(s.name)}"`)}</div>
        <div class="d">${esc(s.description)}</div>
        ${s.mcp ? `<div class="meta small">${s.mcp_enabled == null ? `<span class="tag">Werkzeuge nicht eingerichtet</span>` : s.mcp_enabled === s.enabled ? `<span class="tag cyan">mit Werkzeug ${esc(s.mcp_present.join(" + "))}</span>` : `<span class="tag amber">Werkzeuge ${s.mcp_enabled === "gemischt" ? "teils an" : s.mcp_enabled ? "an" : "aus"} – Schalter gleicht an</span>`}${s.access == null ? "" : s.access ? ' <span class="tag cyan">Zugang hinterlegt</span>' : ' <span class="tag amber">Kein Zugang hinterlegt – nur Lesen</span>'}</div>` : ""}
        <div class="foot">${s.own ? '<span class="tag cyan">eigener</span>' : ""}${s.tags.slice(0, 3).map((t) => `<span class="tag">${esc(t)}</span>`).join("")}<span class="grow"></span>
          ${s.probe ? `<button class="btn small ghost" data-probe="${esc(s.name)}">Testen</button>` : ""}${s.editable ? `<button class="btn small ghost" data-edit="${esc(s.dir)}">Bearbeiten</button>` : ""}${s.own ? `<button class="btn small danger" data-del="${esc(s.dir)}">Löschen</button>` : ""}</div></div>`).join("") || `<div class="empty">Keine Skills gefunden.</div>`);
    $$("[data-sw]", $("#sgrid")).forEach((c) => c.onchange = () => { const want = c.checked; c.checked = !want; change(() => api("/api/skills/toggle", { method: "POST", body: { name: c.dataset.name, enabled: want } }), () => show("skills")); });
    $$("[data-probe]", $("#sgrid")).forEach((b) => b.onclick = () => {
      const sk = d.items.find((x) => x.name === b.dataset.probe), LBL = { wetter: "Wetter", heizung: "Heizung", raeume: "Räume", klima: "Klima", energie: "Strom" };
      openModal({ title: `Test: ${sk.name}`, buttons: [{ label: "Schließen", onClick: closeModal }],
        bodyHTML: `<p class="muted small">Nur lesend – fragt die aktuellen Werte ab und zeigt den Satz, den JARVIS sprechen würde.</p>
          <div class="inline">${sk.probe.map((t) => `<button class="btn small ghost" data-topic="${esc(t)}">${esc(LBL[t] || t)}</button>`).join("")}</div><div id="probeOut"><br><div class="empty">Thema wählen.</div></div>` });
      $$("[data-topic]", $("#modalBody")).forEach((t) => t.onclick = () => busy(t, async () => {
        const r = await api("/api/skills/probe", { method: "POST", body: { name: sk.name, topic: t.dataset.topic } });
        setHTML($("#probeOut"), `<br><p>${esc(r.sentence || "Keine Antwort.")}</p>${r.ok ? "" : `<pre class="mono small">${esc(r.output)}</pre>`}`);
      }));
    });
    $$("[data-edit]", $("#sgrid")).forEach((b) => b.onclick = () => skillEditor(b.dataset.edit, d.categories));
    $$("[data-del]", $("#sgrid")).forEach((b) => b.onclick = () => change(() => api("/api/skills/delete", { method: "POST", body: { dir: b.dataset.del } }), () => show("skills")));
  };
  $("#sq").oninput = (e) => { skillFilter.q = e.target.value; draw(); };
  $("#scat").onchange = (e) => { skillFilter.cat = e.target.value; draw(); };
  $("#sonly").onchange = (e) => { skillFilter.only = e.target.value; draw(); };
  draw();
}
async function skillEditor(dir, cats) {
  if (dir) {
    const c = await api(`/api/skills/content?dir=${encodeURIComponent(dir)}`);
    openModal({ file: `Skill ${dir}`, title: "Skill bearbeiten", bodyHTML: `<p class="hint">Kompletter Inhalt von SKILL.md inkl. Kopfbereich (name, description).</p><textarea id="skText" class="mono" rows="22">${esc(c.text)}</textarea>`,
      buttons: [{ label: "Abbrechen", cls: "ghost", onClick: closeModal }, { label: "Weiter zur Vorschau", cls: "primary", onClick: () => { const t = $("#skText").value; closeModal(); change(() => api("/api/skills/save", { method: "POST", body: { dir, text: t } }), () => show("skills")); } }] });
    return;
  }
  openModal({ file: "Neuer Skill", title: "Skill eintragen", bodyHTML: `
      <div class="grid2"><label class="field"><span>Name (Kurzname)</span><input id="skName" class="mono" placeholder="z. B. einkaufsliste"></label>
      <label class="field"><span>Kategorie</span><input id="skCat" class="mono" list="skCats" value="jarvis"><datalist id="skCats">${cats.map((c) => `<option value="${esc(c)}">`).join("")}</datalist></label></div>
      <label class="field"><span>Beschreibung – wann soll JARVIS den Skill nutzen?</span><input id="skDesc" placeholder="z. B. Einkaufsliste führen: hinzufügen, vorlesen, leeren."><small>Daran erkennt JARVIS, wann der Skill passt. Max. 300 Zeichen.</small></label>
      <label class="field"><span>Anleitung (Markdown)</span><textarea id="skBody" rows="12" placeholder="## Wann nutzen&#10;…&#10;&#10;## Ablauf&#10;1. …"></textarea></label>`,
    buttons: [{ label: "Abbrechen", cls: "ghost", onClick: closeModal }, { label: "Weiter zur Vorschau", cls: "primary", onClick: () => {
      const b = { name: $("#skName").value, category: $("#skCat").value, description: $("#skDesc").value, body: $("#skBody").value };
      closeModal(); change(() => api("/api/skills/save", { method: "POST", body: b }), () => show("skills")); } }] });
}

/* ------------------------------------------------------------ Zeitplaene */
async function viewJobs(view) {
  let d, err = "";
  try { d = await api("/api/jobs"); } catch (e) { err = e.message; d = {}; }
  const jobs = Array.isArray(d) ? d : d.jobs || d.items || [];
  const sched = (j) => typeof j.schedule === "string" ? j.schedule : j.schedule?.display || j.schedule?.expr || j.schedule_display || JSON.stringify(j.schedule || "");
  setHTML(view, `
    <div class="panel span-7"><h3>Geplante Aufgaben</h3>${err ? `<div class="note danger">${esc(err)}</div>` : ""}
      <div class="rows">${jobs.map((j) => { const paused = j.paused || j.enabled === false || j.state === "paused"; return `<div class="row">${dot(paused ? null : true)}
        <div class="grow"><div class="title">${esc(j.name || j.id)}</div><div class="desc">${esc((j.prompt || "").slice(0, 160))}</div>
          <div class="meta mono">${esc(sched(j))}${j.next_run_at ? " · nächster Lauf " + esc(fmtTime(j.next_run_at)) : ""}${j.last_status ? " · zuletzt " + esc(j.last_status) : ""}</div></div>
        <div class="inline"><button class="btn small ghost" data-job="run" data-id="${esc(j.id)}">Jetzt</button>
          <button class="btn small ghost" data-job="${paused ? "resume" : "pause"}" data-id="${esc(j.id)}">${paused ? "Fortsetzen" : "Pausieren"}</button>
          <button class="btn small danger" data-job="delete" data-id="${esc(j.id)}">Löschen</button></div></div>`; }).join("") || `<div class="empty">Noch keine Zeitpläne.</div>`}</div></div>
    <div class="panel span-5"><h3>Neuer Zeitplan</h3>
      <label class="field"><span>Name</span><input id="jName" placeholder="z. B. Morgenbriefing"></label>
      <label class="field"><span>Zeitplan</span><input id="jSched" class="mono" placeholder="0 7 * * 1-5  ·  every 2h  ·  30m"><small>Cron-Ausdruck (Min Std Tag Monat Wochentag), „every 2h“ oder einmalig „30m“.</small></label>
      <label class="field"><span>Auftrag an JARVIS</span><textarea id="jPrompt" rows="5" placeholder="Fasse mir das Wetter und meine Termine für heute zusammen."></textarea></label>
      <div class="note small">Zeitpläne laufen ohne Rückfrage: gefährliche Befehle werden dort automatisch abgelehnt (siehe Bestätigungen).</div><br>
      <button class="btn primary" id="jCreate">Anlegen</button></div>`);
  $$("[data-job]", view).forEach((b) => b.onclick = () => busy(b, async () => {
    if (b.dataset.job === "delete" && !await confirmBox("Zeitplan löschen?", "Der Zeitplan wird entfernt. Das lässt sich nicht rückgängig machen.", "Löschen", true)) return;
    await api(`/api/jobs/${encodeURIComponent(b.dataset.id)}/${b.dataset.job}`, { method: "POST", body: {} }); toast("Erledigt."); show("zeitplaene");
  }));
  $("#jCreate").onclick = (e) => busy(e.target, async () => {
    await api("/api/jobs", { method: "POST", body: { name: $("#jName").value, schedule: $("#jSched").value, prompt: $("#jPrompt").value } });
    toast("Zeitplan angelegt."); show("zeitplaene");
  });
}

/* ------------------------------------------------------------ MCP */
async function viewMcp(view) {
  const d = await api("/api/mcp");
  setHTML(view, `
    <div class="panel span-7"><h3>Eingetragene Server</h3><div class="rows">${d.items.map((s) => `<div class="row">${sw("mcp:" + s.name, s.enabled, `data-name="${esc(s.name)}"`)}
        <div class="grow"><div class="title">${esc(s.name)}</div><div class="meta mono">${esc(s.url || [s.command, ...s.args].join(" "))}</div></div>
        <button class="btn small danger" data-rm="${esc(s.name)}">Entfernen</button></div>`).join("") || `<div class="empty">Keine MCP-Server eingetragen.</div>`}</div></div>
    <div class="panel span-5"><h3>Server eintragen</h3>
      <label class="field"><span>Name</span><input id="mcName" class="mono" placeholder="z. B. homeassistant"></label>
      <label class="field"><span>Art</span><select id="mcType"><option value="url">Entfernt (HTTP-URL)</option><option value="cmd">Lokal (Befehl)</option></select></label>
      <label class="field" id="fUrl"><span>URL</span><input id="mcUrl" class="mono" placeholder="http://homeassistant.local:8123/mcp_server/sse"></label>
      <div id="fCmd" hidden><label class="field"><span>Befehl</span><input id="mcCmd" class="mono" placeholder="npx"></label>
        <label class="field"><span>Argumente (eins pro Zeile)</span><textarea id="mcArgs" class="mono" rows="4"></textarea></label></div>
      <div class="note small">Zugangsdaten für den Server als Variable unter „Schlüssel“ ablegen.</div><br>
      <button class="btn primary" id="mcSave">Weiter zur Vorschau</button></div>`);
  $("#mcType").onchange = (e) => { $("#fUrl").hidden = e.target.value !== "url"; $("#fCmd").hidden = e.target.value === "url"; };
  $$("[data-sw]", view).forEach((c) => c.onchange = () => { const want = c.checked; c.checked = !want; change(() => api("/api/mcp/save", { method: "POST", body: { name: c.dataset.name, action: "toggle", enabled: want } }), () => show("mcp")); });
  $$("[data-rm]", view).forEach((b) => b.onclick = () => change(() => api("/api/mcp/save", { method: "POST", body: { name: b.dataset.rm, action: "remove" } }), () => show("mcp")));
  $("#mcSave").onclick = () => change(() => api("/api/mcp/save", { method: "POST", body: $("#mcType").value === "url"
    ? { name: $("#mcName").value, url: $("#mcUrl").value } : { name: $("#mcName").value, command: $("#mcCmd").value, args: $("#mcArgs").value.split("\n").map((s) => s.trim()).filter(Boolean) } }), () => show("mcp"));
}

/* ------------------------------------------------------------ Bestaetigungen */
async function viewApprovals(view) {
  const a = await api("/api/approvals");
  const modes = [["manual", "Immer fragen", "Jeder als gefährlich erkannte Befehl braucht dein Ja (empfohlen)."],
    ["smart", "Smart", "Ein Hilfsmodell schätzt das Risiko ein und fragt nur bei echten Gefahren."],
    ["off", "Aus", "Keine Rückfragen. Nicht empfohlen."]];
  setHTML(view, `
    <div class="panel span-7"><h3>Gefährliche Befehle</h3>
      <div class="rows">${modes.map(([v, t, h]) => `<label class="row"><input type="radio" name="mode" value="${v}" ${a.mode === v ? "checked" : ""}>
        <div class="grow"><div class="title">${t}${v === "manual" ? ' <span class="tag cyan">aktuell empfohlen</span>' : v === "off" ? ' <span class="tag red">riskant</span>' : ""}</div><div class="desc">${h}</div></div></label>`).join("")}</div>
      <div class="grid3"><label class="field"><span>Wartezeit auf Antwort (s)</span><input id="apT" type="number" min="15" max="3600" value="${esc(a.timeout)}"></label>
        <label class="field"><span>Zeitpläne</span><select id="apCron"><option value="deny">ablehnen</option><option value="approve">erlauben</option></select></label>
        <label class="field"><span>API/Webhooks</span><select id="apUn"><option value="deny">ablehnen</option><option value="approve">erlauben</option></select></label></div>
      <button class="btn primary" id="apSave">Speichern …</button></div>
    <div class="panel span-5"><h3>Immer verbieten</h3><p class="hint">Muster (eins pro Zeile, * als Platzhalter). Diese Befehle blockt Hermes immer – auch mit Bestätigung.</p>
      <textarea id="apDeny" class="mono" rows="10" placeholder="git push --force*&#10;dd if=* of=/dev/*">${esc(a.deny.join("\n"))}</textarea><br><br>
      <button class="btn primary" id="apDenySave">Speichern …</button></div>`);
  $("#apCron").value = a.cron_mode; $("#apUn").value = a.unattended_mode;
  $("#apSave").onclick = () => change(() => api("/api/approvals/save", { method: "POST", body: { mode: $("input[name=mode]:checked", view)?.value, timeout: +$("#apT").value, cron_mode: $("#apCron").value, unattended_mode: $("#apUn").value } }), () => show("regeln"));
  $("#apDenySave").onclick = () => change(() => api("/api/approvals/save", { method: "POST", body: { deny: $("#apDeny").value.split("\n") } }), () => show("regeln"));
}

/* ------------------------------------------------------------ Schluessel */
async function viewEnv(view) {
  const d = await api("/api/env");
  setHTML(view, `
    <div class="panel span-8"><h3>Variablen in ~/.hermes/.env</h3><div class="rows">${d.items.map((v) => `<div class="row">
        <div class="grow"><div class="title mono">${esc(v.name)}</div><div class="meta mono">${esc(v.value || "(leer)")}</div></div>
        ${v.protected ? '<span class="tag amber">gesperrt</span>' : `${v.secret ? '<span class="tag">geheim</span>' : ""}<button class="btn small ghost" data-set="${esc(v.name)}" data-secret="${v.secret ? 1 : ""}">Ändern</button><button class="btn small danger" data-rm="${esc(v.name)}">Entfernen</button>`}</div>`).join("")}</div></div>
    <div class="panel span-4"><h3>Hinzufügen / überschreiben</h3>
      <label class="field"><span>Name</span><input id="evName" class="mono" placeholder="OPENROUTER_API_KEY" autocomplete="off"></label>
      <label class="field"><span>Wert</span><input id="evVal" type="password" class="mono" autocomplete="new-password"><small>Wird nur an den Server geschickt, nie wieder angezeigt.</small></label>
      <button class="btn primary" id="evSave">Weiter zur Vorschau</button>
      <div class="note small">API_SERVER_* verbinden Hermes mit der Handy-Oberfläche und sind gesperrt.</div></div>`);
  const save = (name, value, remove = false) => change(() => api("/api/env/save", { method: "POST", body: { name, value, remove } }), () => show("schluessel"));
  $$("[data-set]", view).forEach((b) => b.onclick = () => { $("#evName").value = b.dataset.set; $("#evVal").type = b.dataset.secret ? "password" : "text"; $("#evVal").focus(); });
  $$("[data-rm]", view).forEach((b) => b.onclick = () => save(b.dataset.rm, "", true));
  $("#evSave").onclick = () => { const v = $("#evVal").value; $("#evVal").value = ""; save($("#evName").value, v); };
}

/* ------------------------------------------------------------ Sprache */
async function viewVoice(view) {
  const [u, c] = await Promise.all([api("/api/ui-settings"), api("/api/config")]);
  const s = u.settings, cfg = c.config;
  const ls = s.length_scale ?? 0.95;
  const stops = (cfg.voice?.stop_phrases || []).join(", ");
  setHTML(view, `
    <div class="panel span-6"><h3>Stimme am Handy</h3>
      ${u.exists ? "" : `<div class="note warn">Noch keine ui.json – Standardwerte der Oberfläche aktiv. Speichern legt sie an.</div><br>`}
      <label class="field"><span>Piper-Stimme</span><select id="vVoice">${u.voices.map((v) => `<option ${v === (s.piper_voice || "de_DE-thorsten-medium") ? "selected" : ""}>${esc(v)}</option>`).join("")}</select><small>„high“ klingt natürlicher, braucht aber mehr Rechenzeit.</small></label>
      <label class="field"><span>Sprechtempo <b id="vLsOut"></b></span><input id="vLs" type="range" min="0.7" max="1.3" step="0.05" value="${esc(ls)}"><small>Kleiner = schneller (length_scale).</small></label>
      <div class="row"><div class="grow"><div class="title">Bei Sprachfragen nachdenken</div><div class="desc">Aus = schnelle Antworten (~2 s). An = gründlicher, aber deutlich langsamer.</div></div>${sw("reason", !!s.reasoning_voice, 'id="vReason"')}</div>
      <div class="row"><div class="grow"><div class="title">Wecken mit „Hey Jarvis“</div><div class="desc">Das Mikro läuft dann ständig mit, aber nichts wird aufgezeichnet oder gesendet, bevor „Hey Jarvis“ erkannt ist (nur kurzer Puffer im Arbeitsspeicher des Handys).</div></div>${sw("wake", !!s.wake_word, 'id="vWake"')}</div>
      <div class="row"><div class="grow"><div class="title">Nach Antwort weiter zuhören</div><div class="desc">JARVIS fragt nach jeder Antwort kurz nach und hört einige Sekunden ohne „Hey Jarvis“ zu. Beenden mit „Nein danke“, „Das war’s“ oder „Gute Nacht“.</div></div>${sw("followup", s.follow_up ?? true, 'id="vFollow"')}</div>
      <label class="field"><span>Wartezeit auf Antwort (Sekunden)</span><input id="vFollowT" type="number" min="4" max="30" step="1" value="${esc(s.follow_up_timeout_s ?? 8)}"><small>4 bis 30 Sekunden, Standard 8.</small></label>
      <label class="field"><span>Betriebsmodus</span><select id="vMode"><option value="live">Live (echtes Gehirn)</option><option value="demo">Demo (ohne Sprachmodell)</option></select></label>
      <div class="inline"><button class="btn ghost" id="vTest">▶ Probehören</button><span class="grow"></span><button class="btn primary" id="vSave">Speichern …</button></div>
      <audio id="vAudio" hidden></audio></div>
    <div class="panel span-6"><h3>Hermes-Sprache</h3>
      <div class="grid2"><label class="field"><span>Erkennungssprache</span><input id="hLang" class="mono" value="${esc(cfg.stt?.language || "de")}"></label>
        <label class="field"><span>STT-Modell</span><input id="hStt" class="mono" value="${esc(cfg.stt?.openai?.model || "")}" disabled><small>Parakeet über den STT-Router.</small></label></div>
      <label class="field"><span>Stopp-Wörter (durch Komma getrennt)</span><input id="hStop" value="${esc(stops)}"><small>Beenden eine laufende Sprachausgabe.</small></label>
      <button class="btn primary" id="hSave">Speichern …</button></div>`);
  $("#vMode").value = s.mode || "live";
  const out = () => { $("#vLsOut").textContent = (+$("#vLs").value).toFixed(2).replace(".", ","); }; $("#vLs").oninput = out; out();
  $("#vSave").onclick = () => change(() => api("/api/ui-settings/save", { method: "POST", body: { piper_voice: $("#vVoice").value, length_scale: +$("#vLs").value, reasoning_voice: $("#vReason").checked, wake_word: $("#vWake").checked, follow_up: $("#vFollow").checked, follow_up_timeout_s: Math.round(+$("#vFollowT").value), mode: $("#vMode").value } }), () => show("sprache"));
  $("#hSave").onclick = () => change(() => api("/api/config/multi", { method: "POST", body: { desc: "Hermes-Spracheinstellungen", changes: { "stt.language": $("#hLang").value.trim() || "de", "voice.stop_phrases": $("#hStop").value.split(",").map((x) => x.trim()).filter(Boolean) } } }), () => show("sprache"));
  $("#vTest").onclick = (e) => busy(e.target, async () => {
    const r = await api("/api/tts-test", { method: "POST", body: { text: "Guten Tag. Alle Systeme sind bereit." }, raw: true });
    const a = $("#vAudio"); a.src = URL.createObjectURL(await r.blob()); await a.play();
  });
}

/* ------------------------------------------------------------ Handy */
async function viewPhone(view) {
  const p = await api("/api/phone"), s = p.status || {};
  actions(`<button class="btn ghost" id="phRefresh">Aktualisieren</button>`).querySelector("#phRefresh").onclick = () => show("handy");
  const kv = (k, v) => `<div class="row"><div class="grow desc">${k}</div><div class="mono">${v ?? "–"}</div></div>`;
  setHTML(view, `
    <div class="panel span-5"><div class="panel-head"><h3>Zustand</h3>${dot(p.reachable && !p.error ? true : p.reachable ? null : false)}</div>
      ${!p.configured || p.error ? `<div class="note ${p.reachable ? "warn" : "danger"}">${!p.reachable ? `Handy (${esc(p.host)}) ist nicht erreichbar.` : !p.configured ? "Die Handy-Steuerung ist noch nicht eingerichtet." : esc(p.error)}</div><br>` : ""}
      ${s.akku_prozent != null ? `<div class="kpi"><span class="label">Akku ${esc(s.akku_prozent)} %${s.laedt ? " · lädt" : ""}${s.akku_temp != null ? ` · ${esc(s.akku_temp)} °C` : ""}</span><div class="bar"><i data-w="${+s.akku_prozent}"></i></div></div><br>` : ""}
      <div class="rows">${kv("IP-Adresse", esc(s.ip || p.host))}${kv("WLAN", s.wlan_ssid ? `${esc(s.wlan_ssid)} · ${esc(s.wlan_signal_dbm)} dBm` : null)}
        ${kv("Läuft seit", s.uptime_s != null ? fmtDur(s.uptime_s) : null)}${kv("Kiosk", s.kiosk_laeuft == null ? null : s.kiosk_laeuft ? "läuft" : "aus")}${kv("NixOS-Generation", esc(s.nixos_generation))}</div></div>
    <div class="panel span-7"><h3>Steuerung</h3>
      <div class="inline"><button class="btn" data-ph="kiosk-reload">Kiosk neu laden</button><button class="btn ghost" data-ph="bildschirm" data-v="an">Bildschirm an</button>
        <button class="btn ghost" data-ph="bildschirm" data-v="aus">Bildschirm aus</button><span class="grow"></span><button class="btn danger" id="phReboot">Handy neu starten</button></div><br>
      <div class="grid2"><label class="field"><span>Helligkeit <b id="brOut">${esc(s.helligkeit_prozent ?? "–")}</b> %</span><input type="range" id="phBr" min="5" max="100" step="5" value="${esc(s.helligkeit_prozent ?? 60)}"></label>
        <label class="field"><span>Lautstärke <b id="voOut">${esc(s.lautstaerke_prozent ?? "–")}</b> %</span><input type="range" id="phVo" min="0" max="100" step="5" value="${esc(s.lautstaerke_prozent ?? 70)}"></label></div>
      <p class="hint small">Neustart dauert bis zur fertigen JARVIS-Oberfläche etwa 100 Sekunden.</p>
      ${p.pubkey ? `<details><summary class="small muted">Technik: eingeschränkter SSH-Schlüssel der Verwaltung</summary><pre class="code mono">${esc(p.pubkey)}</pre>
        <p class="hint small">Auf dem Handy nur mit command=-Restriktion (status, reboot, kiosk-reload, helligkeit, lautstaerke, bildschirm) hinterlegt.</p></details>` : ""}</div>`);
  const act = (action, body = {}) => api(`/api/phone/${action}`, { method: "POST", body }).then(() => toast("Erledigt."));
  $$("[data-ph]", view).forEach((b) => b.onclick = () => busy(b, () => act(b.dataset.ph, { value: b.dataset.v })));
  $("#phReboot").onclick = async () => { if (await confirmBox("Handy neu starten?", "Das Handy startet neu. JARVIS ist am Handy etwa 100 Sekunden nicht erreichbar.", "Neu starten", true)) busy($("#phReboot"), () => act("reboot", { confirm: "NEUSTART" })); };
  const slider = (id, outId, action) => { let t; $(id).oninput = (e) => { $(outId).textContent = e.target.value; clearTimeout(t); t = setTimeout(() => act(action, { value: +e.target.value }).catch((er) => toast(er.message, "err")), 400); }; };
  slider("#phBr", "#brOut", "helligkeit"); slider("#phVo", "#voOut", "lautstaerke");
}

/* ------------------------------------------------------------ Dienste */
async function viewServices(view) {
  const d = await api("/api/services");
  const checks = [["config", "Konfiguration prüfen", "hermes config check"], ["doctor", "Hermes-Doktor", "hermes doctor"], ["status", "Komponenten-Status", "hermes status"], ["cron", "Zeitplaner", "hermes cron status"], ["skills", "Skill-Liste", "hermes skills list"]];
  setHTML(view, `
    <div class="panel span-6"><h3>Dienste</h3>${d.ctl ? "" : `<div class="note warn">Neustart-Helfer nicht eingerichtet.</div>`}
      <div class="rows">${d.units.map((u) => `<div class="row">${dot(u.active === "active" ? true : u.active === "activating" ? null : false)}
        <div class="grow"><div class="title">${esc(u.label)}</div><div class="meta mono">${esc(u.unit)} · seit ${esc(u.since || "–")}${u.restarts && u.restarts !== "0" ? ` · ${esc(u.restarts)} Abstürze` : ""}</div></div>
        <button class="btn small" data-restart="${esc(u.id)}" ${d.ctl ? "" : "disabled"}>Neu starten</button></div>`).join("")}</div>
      ${d.last ? `<p class="hint small">Letzter Neustart: ${esc(d.last.unit)} – ${esc(d.last.message)} (${esc(fmtTime(d.last.time))})</p>` : ""}</div>
    <div class="panel span-6"><h3>Prüfungen</h3><div class="inline">${checks.map(([k, l, c]) => `<button class="btn small ghost" data-check="${k}" title="${esc(c)}">${esc(l)}</button>`).join("")}</div><br>
      <pre class="out" id="chkOut">Eine Prüfung wählen …</pre></div>`);
  $$("[data-restart]", view).forEach((b) => b.onclick = () => busy(b, () => restartUnit(b.dataset.restart).then(() => show("dienste"))));
  $$("[data-check]", view).forEach((b) => b.onclick = () => busy(b, async () => { $("#chkOut").textContent = "Läuft …"; const r = await api("/api/doctor", { method: "POST", body: { which: b.dataset.check } }); $("#chkOut").textContent = (r.ok ? "✓ " : "✗ ") + b.textContent + "\n\n" + r.output; }));
}

/* ------------------------------------------------------------ Protokolle */
let logOpt = { source: "agent", level: "", q: "", lines: 300, live: false };
async function viewLogs(view) {
  setHTML(view, `<div class="panel span-12"><div class="toolbar">
      <select id="lgSrc"></select><select id="lgLvl"><option value="">Alle Stufen</option><option value="warning">Warnungen + Fehler</option><option value="error">Nur Fehler</option></select>
      <input id="lgQ" placeholder="Filtern …" value="${esc(logOpt.q)}"><select id="lgN"><option>100</option><option>300</option><option>1000</option><option>3000</option></select>
      <label class="inline small">${sw("live", logOpt.live, 'id="lgLive"')} Live</label><span class="grow"></span><button class="btn small ghost" id="lgGo">Neu laden</button></div>
      <div class="log" id="lgOut"></div></div>`);
  $("#lgLvl").value = logOpt.level; $("#lgN").value = String(logOpt.lines);
  const load = async () => {
    const d = await api(`/api/logs?source=${encodeURIComponent(logOpt.source)}&level=${logOpt.level}&lines=${logOpt.lines}&q=${encodeURIComponent(logOpt.q)}`);
    const sel = $("#lgSrc"); if (!sel.options.length) { setHTML(sel, Object.entries(d.sources).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")); sel.value = logOpt.source; }
    const out = $("#lgOut"), atEnd = out.scrollTop + out.clientHeight >= out.scrollHeight - 30;
    setHTML(out, d.lines.map((l) => `<div data-l="${/ERROR|CRITICAL|Traceback|Fehler/.test(l) ? "e" : /WARNING|WARN/.test(l) ? "w" : ""}">${esc(l)}</div>`).join("") || `<div class="empty">Keine Einträge.</div>`);
    if (atEnd || !out.dataset.init) { out.scrollTop = out.scrollHeight; out.dataset.init = 1; }
  };
  $("#lgSrc").onchange = (e) => { logOpt.source = e.target.value; load(); };
  $("#lgLvl").onchange = (e) => { logOpt.level = e.target.value; load(); };
  $("#lgN").onchange = (e) => { logOpt.lines = +e.target.value; load(); };
  let t; $("#lgQ").oninput = (e) => { logOpt.q = e.target.value; clearTimeout(t); t = setTimeout(load, 350); };
  $("#lgGo").onclick = load;
  $("#lgLive").onchange = (e) => { logOpt.live = e.target.checked; };
  refreshTimer = setInterval(() => { if (logOpt.live && current === "protokolle" && !document.hidden) load().catch(() => {}); }, 3000);
  await load();
}

/* ------------------------------------------------------------ Sicherungen, Experte, Konto */
async function viewBackups(view) {
  const [b, au] = await Promise.all([api("/api/backups"), api("/api/audit")]);
  actions(`<a class="btn" href="/api/export" download>Export herunterladen</a>`);
  setHTML(view, `
    <div class="panel span-7"><h3>Sicherungen</h3><div class="rows">${b.items.slice(0, 60).map((x) => `<div class="row"><div class="grow"><div class="title">${esc(x.file)}</div>
        <div class="desc">${esc(x.reason)}</div><div class="meta">${esc(fmtTime(x.time))} · ${fmtBytes(x.size)} · Stand <b>vor</b> der Änderung</div></div>
        <button class="btn small ghost" data-restore="${esc(x.id)}">Wiederherstellen …</button></div>`).join("") || `<div class="empty">Noch keine Änderungen über die Verwaltung.</div>`}</div></div>
    <div class="panel span-5"><h3>Expertenmodus: Einstellung setzen</h3>
      <p class="hint">Beliebiger Pfad in config.yaml, Wert als YAML. Auch hier: Vorschau, Sicherung, Prüfung.</p>
      <label class="field"><span>Pfad</span><input id="exPath" class="mono" placeholder="agent.max_turns"></label>
      <label class="field"><span>Wert (YAML)</span><textarea id="exVal" class="mono" rows="3" placeholder="200"></textarea></label>
      <div class="inline"><button class="btn danger small" id="exRm">Entfernen …</button><span class="grow"></span><button class="btn primary" id="exSet">Setzen …</button></div>
      <br><h3>Konto</h3>
      <label class="field"><span>Bisheriges Passwort</span><input id="pwOld" type="password" autocomplete="current-password"></label>
      <label class="field"><span>Neues Passwort (mind. 10 Zeichen)</span><input id="pwNew" type="password" autocomplete="new-password"></label>
      <div class="inline"><button class="btn ghost small" id="pwAll">Alle Geräte abmelden</button><span class="grow"></span><button class="btn primary small" id="pwSave">Passwort ändern</button></div></div>
    <div class="panel span-12"><h3>Änderungsprotokoll</h3><div class="log">${au.lines.slice().reverse().map((l) => `<div>${esc(l)}</div>`).join("") || `<div class="empty">Leer.</div>`}</div></div>`);
  $$("[data-restore]", view).forEach((x) => x.onclick = () => change(() => api(`/api/backups/${encodeURIComponent(x.dataset.restore)}/restore`, { method: "POST", body: {} }), () => show("sicherungen")));
  $("#exSet").onclick = () => change(() => api("/api/config/set", { method: "POST", body: { path: $("#exPath").value, value: $("#exVal").value } }), () => show("sicherungen"));
  $("#exRm").onclick = () => change(() => api("/api/config/set", { method: "POST", body: { path: $("#exPath").value, remove: true } }), () => show("sicherungen"));
  $("#pwSave").onclick = (e) => busy(e.target, async () => { await api("/api/auth/password", { method: "POST", body: { old: $("#pwOld").value, new: $("#pwNew").value } }); $("#pwOld").value = $("#pwNew").value = ""; toast("Passwort geändert. Andere Geräte sind abgemeldet."); });
  $("#pwAll").onclick = async () => { if (await confirmBox("Überall abmelden?", "Alle angemeldeten Browser – auch dieser – werden abgemeldet.", "Abmelden")) { await api("/api/auth/logout-all", { method: "POST", body: {} }); showLogin(); } };
}

/* ------------------------------------------------------------ Login */
let setupMode = false;
function moveOrb(toLogin) { const w = $(".orb-wrap"); (toLogin ? $("#loginOrbSlot") : $(".side-head")).prepend(w); }
async function showLogin() {
  clearInterval(refreshTimer); shell.dataset.auth = "out"; $("#login").hidden = false; moveOrb(true); closeModal();
  let st = { configured: true }; try { st = await (await fetch("/api/auth/state")).json(); } catch { /* */ }
  setupMode = !st.configured;
  $("#setupFields").hidden = !setupMode; $("#pw2Field").hidden = !setupMode;
  $("#pwLabel").textContent = setupMode ? "Neues Passwort (mind. 10 Zeichen)" : "Passwort";
  $("[name=password]").autocomplete = setupMode ? "new-password" : "current-password";
  $("#loginBtn").textContent = setupMode ? "Passwort festlegen" : "Anmelden";
  $("#setupHint").textContent = st.setupHint || "";
  shell.dataset.state = "idle"; window.Orb && Orb.set({ state: "idle" });
  setTimeout(() => (setupMode ? $("[name=code]") : $("[name=password]")).focus(), 50);
}
$("#loginForm").addEventListener("submit", async (e) => {
  e.preventDefault(); const f = e.target, err = $("#loginErr"); err.textContent = "";
  if (setupMode && f.password.value !== f.password2.value) { err.textContent = "Die Passwörter stimmen nicht überein."; return; }
  shell.dataset.state = "thinking"; window.Orb && Orb.set({ state: "thinking" });
  try {
    await api(setupMode ? "/api/auth/setup" : "/api/auth/login", { method: "POST", body: { password: f.password.value, code: f.code.value } });
    f.reset(); start();
  } catch (ex) { err.textContent = ex.message; shell.dataset.state = "error"; window.Orb && Orb.set({ state: "error" }); }
});
$("#btnLogout").addEventListener("click", async () => { await api("/api/auth/logout", { method: "POST", body: {} }).catch(() => {}); showLogin(); });

/* ------------------------------------------------------------ Start */
function tick() { $("#clock").textContent = new Date().toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" }); }
async function start() {
  const st = await (await fetch("/api/auth/state")).json();
  if (!st.loggedIn) return showLogin();
  $("#login").hidden = true; shell.dataset.auth = "in"; moveOrb(false);
  if (!$("#nav").children.length) buildNav();
  await show(location.hash.slice(1) || "uebersicht");
  pollStatus();
}
buildNav(); tick(); setInterval(tick, 10000); setInterval(() => { if (shell.dataset.auth === "in" && !document.hidden) pollStatus(); }, 15000);
start();
