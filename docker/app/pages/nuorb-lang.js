// NuOrb (Docker): gemeinsame Sprachwahl der Zusatzseiten. Englisch ist Grundtext im HTML, Deutsch die Alternative.
// Reihenfolge wie im Admin-Panel (NuOrb-Admin i18n.js): ?lang=, Wahl im Browser (localStorage nuorb-admin-lang),
// Server-Einstellung ui_lang (de|en), bei „auto“ die Browsersprache.
window.NuI18n = (function () {
  const KEY = "nuorb-admin-lang";
  const ok = (v) => (v === "de" || v === "en" ? v : null);
  const stored = () => { const q = ok(new URLSearchParams(location.search).get("lang")); if (q) return q;
                         try { return ok(localStorage.getItem(KEY)); } catch (e) { return null; } };
  const browser = () => (String(navigator.language || "en").toLowerCase().startsWith("de") ? "de" : "en");
  const I = { lang: stored() || browser(), brand: "NuOrb" };

  // Deutsche Server-Texte (Modellhinweise, Gehirn-Beschreibung, Meldungen der Verwaltung) übersetzen – mit dem
  // Wörterbuch der NuOrb-Verwaltung (/static/i18n-en.js: Schlüssel = deutscher Text, {0} … = eingesetzte Werte)
  let muster = null;
  I.tr = (s) => {
    s = String(s ?? "");
    const EN = window.I18N_EN;
    if (I.lang !== "en" || !EN || !s) return s;
    const marke = (t) => String(t).replace(/\bNUORB\b/g, I.brand);
    if (EN[s] !== undefined) return marke(EN[s]);
    if (!muster) {
      muster = Object.keys(EN).filter((k) => /\{\d\}/.test(k)).map((k) => {
        const esc = k.replace(/[.*+?^$()|[\]\\]/g, "\\$&").replace(/\\?\{(\d)\\?\}/g, "(?<p$1>.+?)");
        try { return [new RegExp("^" + esc + "$"), EN[k]]; } catch (e) { return null; }   // z. B. {0} doppelt
      }).filter(Boolean);
    }
    for (const [re, en] of muster) {
      const m = s.match(re);
      if (m) return marke(en.replace(/\{(\d)\}/g, (_, i) => I.tr((m.groups || {})["p" + i] ?? "")));
    }
    return s;
  };

  // Platzhalter {brand} in Texten ersetzen
  I.fmt = (s) => String(s).split("{brand}").join(I.brand);

  // API-Aufruf mit Sprachkopf (Fehlermeldungen des Servers kommen dann in derselben Sprache)
  I.api = async (path, body) => {
    const h = { "X-UI-Lang": I.lang };
    const r = await fetch(path, body === undefined ? { cache: "no-store", headers: h } : {
      method: "POST", headers: { ...h, "Content-Type": "application/json", "X-NuOrb": "1" }, body: JSON.stringify(body) });
    if (r.status === 401) { location.href = "/"; throw new Error("login"); }
    const d = await r.json().catch(() => ({}));
    if (!r.ok) { const e = new Error(d.detail || r.status); e.data = d; throw e; }
    return d;
  };

  // Server-Zustand übernehmen und Seite übersetzen. dict = { de: {...}, en: {...} } für [data-t]-Elemente.
  I.init = (state, dict, title) => {
    if (!stored()) I.lang = ok(state.ui_lang) || browser();
    if (state.brand) I.brand = state.brand;
    const t = dict[I.lang] || dict.en;
    document.documentElement.lang = I.lang;
    document.querySelectorAll("[data-t]").forEach((el) => { if (t[el.dataset.t] !== undefined) el.textContent = I.fmt(t[el.dataset.t]); });
    document.querySelectorAll("[data-t-alt]").forEach((el) => { if (t[el.dataset.tAlt] !== undefined) el.alt = I.fmt(t[el.dataset.tAlt]); });
    if (title) document.title = I.brand + " · " + I.fmt(t[title] || title);
    const sw = document.getElementById("langSwitch");
    if (sw) {
      sw.replaceChildren();
      for (const [code, label] of [["de", "DE"], ["en", "EN"]]) {   // Reihenfolge wie im Admin-Panel
        const b = document.createElement("button"); b.type = "button"; b.textContent = label; b.dataset.lang = code;
        b.setAttribute("aria-pressed", String(code === I.lang));
        b.addEventListener("click", () => {
          try { localStorage.setItem(KEY, code); } catch (e) {}
          const u = new URL(location.href); u.searchParams.delete("lang"); location.replace(u.href);   // ?lang= würde die Wahl überstimmen
        });
        sw.append(b);
      }
    }
    I.chrome();
    return t;
  };

  // Auf jeder Zusatzseite: Versionszeile mit „Auf Update prüfen“ (oben) und Spendenhinweis (unten, immer sichtbar)
  const CT = {
    de: { check: "Auf Update prüfen", checking: "Prüfe …", current: "Aktuell.", newer: "Update verfügbar: {v}", notes: "Versionshinweise",
          failed: "Prüfung fehlgeschlagen.", foot: "NuOrb ist kostenlos und quelloffen. Wenn es dir gefällt, freue ich mich über einen Kaffee:" },
    en: { check: "Check for updates", checking: "Checking …", current: "Up to date.", newer: "Update available: {v}", notes: "Release notes",
          failed: "Check failed.", foot: "NuOrb is free and open source. If you like it, you can buy me a coffee:" },
  };
  function renderVer(bar, st, justChecked) {
    const c = CT[I.lang] || CT.en;
    bar.replaceChildren();
    bar.classList.toggle("newer", !!st.newer);
    const label = document.createElement("span"); label.className = "ver-label"; label.textContent = st.label || "";
    bar.append(label);
    if (st.enabled) {
      const b = document.createElement("button"); b.type = "button"; b.className = "btn small"; b.textContent = c.check;
      b.addEventListener("click", async () => {
        b.disabled = true; b.textContent = c.checking;
        try { renderVer(bar, await I.api("/api/update", { check: true }), true); }
        catch (e) { b.disabled = false; b.textContent = c.check; }
      });
      bar.append(b);
    }
    const s = document.createElement("span"); s.className = "ver-status";
    if (st.newer) {
      const strong = document.createElement("strong"); strong.textContent = c.newer.replace("{v}", st.latest); s.append(strong);
      if (st.url) { const a = document.createElement("a"); a.href = st.url; a.target = "_blank"; a.rel = "noopener noreferrer"; a.textContent = c.notes; s.append(" ", a); }
    } else if (st.error) s.textContent = c.failed;
    else if (justChecked) s.textContent = c.current;
    if (s.childNodes.length) bar.append(s);
  }
  I.chrome = () => {
    const main = document.querySelector("main");
    if (!main || document.getElementById("verBar")) return;
    const c = CT[I.lang] || CT.en;
    const bar = document.createElement("div"); bar.className = "ver-bar"; bar.id = "verBar";
    const top = main.querySelector(".top");
    if (top) top.after(bar); else main.prepend(bar);
    I.api("/api/update").then((st) => renderVer(bar, st)).catch(() => bar.remove());
    const foot = document.createElement("footer"); foot.className = "page-foot";
    const a = document.createElement("a"); a.href = "https://www.paypal.com/paypalme/HenryMeinekat"; a.target = "_blank";
    a.rel = "noopener noreferrer"; a.textContent = "PayPal ☕";
    foot.append(c.foot + " ", a);
    main.append(foot);
  };
  return I;
})();
