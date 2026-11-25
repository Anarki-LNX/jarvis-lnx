// Admin – Sprache und Marke (vor admin.js geladen). Muster wie jarvis-ui: Schluessel = deutscher Originaltext,
// Englisch aus I18N_EN (i18n-en.js). Schluessel mit {0}, {1} … sind Muster fuer Texte mit eingesetzten Werten
// (auch Servermeldungen). Danach wird die Marke ersetzt: Platzhalter JARVIS -> Name des Assistenten, „Hey Jarvis“ -> Weckwort.
// Uebersetzt wird automatisch alles, was im DOM landet (MutationObserver): Textknoten und title/placeholder/
// aria-label/alt. Ausgenommen: Eingabefelder, <pre>/<code>, Diffs und alles unter [data-noi18n].
// Sprache: eigene Wahl (localStorage) > Server-Einstellung ui_lang (de|en) > Browser-Sprache.
(function () {
  "use strict";
  const LS = "nuorb-admin-lang";  // geteilt mit den Docker-Seiten (/static/docker/*)
  const cfg = { brand: "NuOrb", assistant_name: "", wake_phrase: "", ui_lang: "", server: "" };
  let choice = null, lang = "de";
  try { choice = localStorage.getItem(LS); } catch (e) { /* privat */ }
  const qp = new URLSearchParams(location.search).get("lang");
  if (qp === "de" || qp === "en") choice = qp;

  function resolve() {
    let l = choice || cfg.ui_lang || "auto";
    if (l !== "de" && l !== "en") l = String(navigator.language || "en").toLowerCase().startsWith("de") ? "de" : "en";
    lang = l;
    document.documentElement.lang = lang;
  }
  resolve();

  const EN = () => window.I18N_EN || {};
  const name = () => cfg.assistant_name || cfg.brand;
  const cap = (b) => (b === b.toUpperCase() ? b.charAt(0) + b.slice(1).toLowerCase() : b);
  const wake = () => cfg.wake_phrase || "Hey " + cap(name());
  const brandify = (s) => String(s).replace(/Hey,? Jarvis/g, wake()).replace(/\bJARVIS\b/g, name());
  const norm = (s) => String(s).replace(/\s+/g, " ").trim();
  const reEsc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

  // Muster aus Schluesseln mit Platzhaltern; spezifischste (meiste feste Zeichen) zuerst.
  let pats = null;
  function patterns() {
    if (pats) return pats;
    pats = [];
    for (const [k, v] of Object.entries(EN())) {
      if (v == null || !/\{\d+\}/.test(k)) continue;
      const lit = k.replace(/\{\d+\}/g, "");
      if (lit.replace(/[\s·:,.()–\-/]/g, "").length < 2) continue;  // zu unspezifisch
      const order = [];
      const src = k.split(/(\{\d+\})/).map((p) => {
        const m = /^\{(\d+)\}$/.exec(p);
        if (m) { order.push(+m[1]); return "([\\s\\S]*?)"; }
        return reEsc(p);
      }).join("");
      pats.push({ re: new RegExp("^" + src + "$"), en: v, order, w: lit.length });
    }
    pats.sort((a, b) => b.w - a.w);
    return pats;
  }

  function lookup(core, depth) {
    const d = EN();
    if (d[core] != null) return d[core];
    if (depth > 1) return null;
    for (const p of patterns()) {
      const m = p.re.exec(core);
      if (!m) continue;
      const vals = {};
      p.order.forEach((n, i) => { const x = m[i + 1]; vals[n] = x && /[A-Za-zÄÖÜäöüß]/.test(x) ? (lookup(norm(x), depth + 1) ?? x) : x; });
      return p.en.replace(/\{(\d+)\}/g, (_, n) => (vals[n] != null ? vals[n] : ""));
    }
    return null;
  }

  // Ganzer Text (Whitespace drumherum bleibt erhalten)
  function tr(s) {
    s = String(s ?? "");
    if (lang === "en") {
      const core = norm(s);
      if (core && /[A-Za-zÄÖÜäöüß]/.test(core)) {
        const en = lookup(core, 0);
        if (en != null) {
          const lead = /^\s*/.exec(s)[0], trail = /\s*$/.exec(s)[0];
          s = lead + en + trail;
        }
      }
    }
    return brandify(s);
  }
  // t("Deutscher Text {0}", [wert]) – fuer Code, der Texte selbst zusammensetzt
  function t(de, vals) {
    let s = lang === "en" ? (EN()[de] != null ? EN()[de] : de) : de;
    if (vals) s = s.replace(/\{(\d+)\}/g, (m, n) => (vals[n] != null ? String(vals[n]) : m));
    return brandify(s);
  }

  // ------------------------------------------------------------ DOM
  const SKIP = "textarea,pre,code,script,style,title,.diff,.out,[data-noi18n]";
  const ATTRS = ["title", "placeholder", "aria-label", "alt"];
  const origText = new WeakMap(), setText = new WeakMap(), origAttr = new WeakMap();
  let paused = false;

  function doText(n) {
    const p = n.parentElement;
    if (!p || p.closest(SKIP)) return;
    const cur = n.nodeValue;
    if (setText.get(n) !== cur) origText.set(n, cur);  // neuer Inhalt von der App
    const out = tr(origText.get(n));
    if (out !== cur) { n.nodeValue = out; }
    setText.set(n, n.nodeValue);
  }
  function doAttrs(el) {
    if (el.closest(SKIP) && !/^(INPUT|TEXTAREA)$/.test(el.tagName)) return;
    let o = origAttr.get(el);
    for (const a of ATTRS) {
      if (!el.hasAttribute(a)) continue;
      const v = el.getAttribute(a);
      if (!o) { o = {}; origAttr.set(el, o); }
      if (o["_set_" + a] !== v) o[a] = v;
      const out = tr(o[a]);
      if (out !== v) el.setAttribute(a, out);
      o["_set_" + a] = out;
    }
  }
  function walk(root) {
    if (root.nodeType === 3) { doText(root); return; }
    if (root.nodeType !== 1 && root.nodeType !== 9 && root.nodeType !== 11) return;
    if (root.nodeType === 1) doAttrs(root);
    const tw = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
    for (let n = tw.nextNode(); n; n = tw.nextNode()) { if (n.nodeType === 3) doText(n); else doAttrs(n); }
  }
  const mo = new MutationObserver((list) => {
    if (paused) return;
    paused = true;
    try {
      for (const m of list) {
        if (m.type === "characterData") doText(m.target);
        else if (m.type === "attributes") doAttrs(m.target);
        else m.addedNodes.forEach(walk);
      }
    } finally { mo.takeRecords(); paused = false; }
  });
  function observe() {
    walk(document.body);
    mo.observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ATTRS });
  }
  if (document.body) observe(); else document.addEventListener("DOMContentLoaded", observe);

  function refresh() { pats = null; resolve(); mo.takeRecords(); walk(document.body); mo.takeRecords(); }

  window.I18N = {
    t, tr,
    get lang() { return lang; },
    get choice() { return choice || "auto"; },
    get locale() { return lang === "en" ? "en-US" : "de-DE"; },
    get brand() { return cfg.brand; },
    get name() { return name(); },
    get wake() { return wake(); },
    get server() { return cfg.server; },
    // Server-Konfiguration (aus /api/auth/state); danach alles neu uebersetzen
    configure(c) {
      if (!c) return;
      for (const k of Object.keys(cfg)) if (typeof c[k] === "string" && c[k]) cfg[k] = c[k];
      refresh();
    },
    setLang(l) {
      choice = l === "de" || l === "en" ? l : null;
      try { if (choice) localStorage.setItem(LS, choice); else localStorage.removeItem(LS); } catch (e) { /* privat */ }
      refresh();
    },
  };
})();
