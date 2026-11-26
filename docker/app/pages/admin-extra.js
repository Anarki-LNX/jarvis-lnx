// NuOrb (Docker): ergänzt das Admin-Panel um „Einrichtung“, „Gerät koppeln“ und „Über“ und blendet die Xiaomi-Handy-Seite aus.
// Läuft nach admin.js; ändert nur die Navigation, die Seiten selbst liegen unter /static/docker/.
(function () {
  // Sprache wie im Admin-Panel (i18n.js von NuOrb-Admin), falls vorhanden; sonst gleiche Regeln wie docker-i18n.js
  const ok = (v) => (v === "de" || v === "en" ? v : null);
  const stored = () => { const q = ok(new URLSearchParams(location.search).get("lang")); if (q) return q;
                         try { return ok(localStorage.getItem("nuorb-admin-lang")); } catch (e) { return null; } };
  const browser = () => (String(navigator.language || "en").toLowerCase().startsWith("de") ? "de" : "en");
  let lang = stored() || browser();
  const L = { de: { group: "Docker", setup: "Einrichtung", pair: "Gerät koppeln", about: "Über" }, en: { group: "Docker", setup: "Setup", pair: "Pair device", about: "About" } };

  function addNav() {
    const nav = document.getElementById("nav");
    if (!nav || !nav.children.length || nav.querySelector("[data-docker]")) return;
    // Xiaomi-Handy und die Link-Kopplung von NuOrb-Admin gibt es im Image nicht; hier koppelt /static/docker/koppeln.html
    for (const v of ["handy", "koppeln"]) { const b = nav.querySelector(`button[data-view="${v}"]`); if (b) b.hidden = true; }
    // Mit i18n.js von NuOrb-Admin: deutsche Texte einsetzen, die Übersetzung (auch beim Umschalten ohne Neuladen) macht I18N
    if (window.I18N && window.I18N_EN) { window.I18N_EN["Einrichtung"] ||= "Setup"; window.I18N_EN["Docker"] ||= "Docker"; window.I18N_EN["Über"] ||= "About"; }
    const t = window.I18N ? L.de : L[lang];
    const g = document.createElement("div"); g.className = "nav-group"; g.textContent = t.group; g.dataset.docker = "1";
    nav.appendChild(g);
    for (const [href, label] of [["/static/docker/koppeln.html", t.pair], ["/static/docker/einrichtung.html", t.setup], ["/static/docker/ueber.html", t.about]]) {
      const b = document.createElement("button"); b.type = "button"; b.dataset.docker = "1";
      b.innerHTML = '<span class="ico" aria-hidden="true">◈</span>'; b.append(document.createTextNode(label));
      b.addEventListener("click", () => { location.href = href; });
      nav.appendChild(b);
    }
  }

  async function check() {
    try {
      const r = await fetch("/api/setup", { cache: "no-store", headers: { "X-UI-Lang": lang } });
      if (!r.ok) return false;              // noch nicht angemeldet
      const s = await r.json();
      lang = (window.I18N && ok(window.I18N.lang)) || stored() || ok(s.ui_lang) || browser();
      addNav();
      if (!s.done && !sessionStorage.getItem("jl.setupSkipped")) location.href = "/static/docker/einrichtung.html";
      return true;
    } catch (e) { return false; }
  }
  // Direktaufruf der nativen Kopplungsseite (#koppeln) -> Kopplung mit Einmal-Code im Image
  const redirect = () => { if (location.hash === "#koppeln") location.replace("/static/docker/koppeln.html"); };
  window.addEventListener("hashchange", redirect); redirect();
  // Nach dem Login baut admin.js die Navigation; so lange beobachten
  const mo = new MutationObserver(() => { if (document.getElementById("nav")?.children.length) check().then((ok) => ok && mo.disconnect()); });
  mo.observe(document.body, { childList: true, subtree: true });
  check();
})();
