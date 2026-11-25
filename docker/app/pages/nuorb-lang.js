// NuOrb (Docker): gemeinsame Sprachwahl der Zusatzseiten. Englisch ist Grundtext im HTML, Deutsch die Alternative.
// Reihenfolge wie im Admin-Panel (jarvis-admin i18n.js): ?lang=, Wahl im Browser (localStorage nuorb-admin-lang),
// Server-Einstellung ui_lang (de|en), bei „auto“ die Browsersprache.
window.NuI18n = (function () {
  const KEY = "nuorb-admin-lang";
  const ok = (v) => (v === "de" || v === "en" ? v : null);
  const stored = () => { const q = ok(new URLSearchParams(location.search).get("lang")); if (q) return q;
                         try { return ok(localStorage.getItem(KEY)); } catch (e) { return null; } };
  const browser = () => (String(navigator.language || "en").toLowerCase().startsWith("de") ? "de" : "en");
  const I = { lang: stored() || browser(), brand: "NuOrb" };

  // Platzhalter {brand} in Texten ersetzen
  I.fmt = (s) => String(s).split("{brand}").join(I.brand);

  // API-Aufruf mit Sprachkopf (Fehlermeldungen des Servers kommen dann in derselben Sprache)
  I.api = async (path, body) => {
    const h = { "X-UI-Lang": I.lang };
    const r = await fetch(path, body === undefined ? { cache: "no-store", headers: h } : {
      method: "POST", headers: { ...h, "Content-Type": "application/json", "X-Jarvis": "1" }, body: JSON.stringify(body) });
    if (r.status === 401) { location.href = "/"; throw new Error("login"); }
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.detail || r.status);
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
    return t;
  };
  return I;
})();
