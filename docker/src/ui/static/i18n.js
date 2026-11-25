// Oberflaechen-Sprache und Marke (vor app.js geladen).
// Hinweis: „JARVIS“ in den deutschen Schluesseln ist nur ein interner Platzhalter fuer den Assistentennamen und wird
// immer ersetzt (sichtbar ist der konfigurierte Name, Standard NuOrb).
// Schluessel = der deutsche Originaltext. Deutsch bleibt also immer exakt wie im Code; Englisch kommt aus I18N_EN
// (i18n-en.js). Platzhalter {name} werden mit vars gefuellt. Danach wird die Marke ersetzt: „JARVIS“ -> brand,
// „Hey Jarvis“ -> wake (Weckwort). Konfiguration: window.JARVIS_CFG (vom Server in index.html gerendert:
// brand, wake_phrase, ui_lang), ueberschreibbar per ?lang=de|en|auto und ?brand=Name (z. B. fuer Screenshots).
(function () {
  "use strict";
  const cfg = window.JARVIS_CFG || {};
  const qp = new URLSearchParams(location.search);
  let lang = String(qp.get("lang") || cfg.ui_lang || "de").toLowerCase();
  if (lang === "auto") lang = String(navigator.language || "de").toLowerCase().startsWith("de") ? "de" : "en";
  if (lang !== "en") lang = "de";
  const clean = (x) => String(x || "").replace(/[^\p{L}\p{N} .\-]/gu, "").trim().slice(0, 24);
  // brand = Produkt (Titel, Manifest, Weckwort), name = wie der Assistent heisst und angesprochen wird
  const brand = clean(qp.get("brand")) || clean(cfg.brand) || "NuOrb";
  let name = clean(qp.get("name")) || (clean(qp.get("brand")) ? brand : "") || clean(cfg.assistant_name) || brand;
  const cap = (b) => (b === b.toUpperCase() ? b.charAt(0) + b.slice(1).toLowerCase() : b);
  let appWake = ""; try { const A = window.NuOrbAndroid || window.JarvisAndroid; if (A && typeof A.wakePhrase === "function") appWake = clean(A.wakePhrase()); } catch (e) { /* alte App */ }
  const wake = clean(qp.get("wake")) || appWake || clean(cfg.wake_phrase) || "Hey " + cap(brand);
  const EN = () => window.I18N_EN || {};

  function fill(s, v) { return v ? String(s).replace(/\{(\w+)\}/g, (m, k) => (v[k] != null ? String(v[k]) : m)) : String(s); }
  function brandify(s) {
    return String(s).replace(/Hey,? Jarvis/g, wake).replace(/\bJARVIS\b/g, name);
  }
  // t("Deutscher Text {x}", {x: 1})
  function t(de, vars) {
    const s = lang === "en" ? (EN()[de] != null ? EN()[de] : de) : de;
    return brandify(fill(s, vars));
  }

  // Statische Texte in index.html (Textknoten + Attribute) einmal beim Start uebersetzen und Marke einsetzen.
  const ATTRS = ["placeholder", "aria-label", "title", "alt"];
  // Originale merken, damit reapply() nach einer Namensaenderung neu rendern kann
  const orig = [];
  function apply(root) {
    root = root || document.body;
    const tw = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const nodes = []; for (let n = tw.nextNode(); n; n = tw.nextNode()) nodes.push(n);
    for (const n of nodes) {
      const raw = n.nodeValue, key = raw.trim();
      if (!key || !/[A-Za-zÄÖÜäöü]/.test(key)) continue;
      const out = t(key);
      if (out !== key || /JARVIS|Hey,? Jarvis/.test(key)) { orig.push([n, null, raw, key]); if (out !== key) n.nodeValue = raw.replace(key, out); }
    }
    for (const el of root.querySelectorAll("[placeholder],[aria-label],[title],[alt]")) {
      for (const a of ATTRS) { const v = el.getAttribute(a); if (v) { const o = t(v); if (o !== v || /JARVIS|Hey,? Jarvis/.test(v)) { orig.push([el, a, v, v]); if (o !== v) el.setAttribute(a, o); } } }
    }
    document.title = brand;
    document.documentElement.lang = lang;
  }

  window.I18N = { t, lang, brand, wake, apply, de: lang === "de", get name() { return name; },
    setName(n) { n = clean(n); if (n) name = n; return name; },
    reapply() { for (const [n, a, raw, key] of orig) { if (a) n.setAttribute(a, t(raw)); else n.nodeValue = raw.replace(key, t(key)); } } };
})();
