// NuOrb (Docker): ergänzt das Admin-Panel um „Einrichtung“ und „Gerät koppeln“ und blendet die Xiaomi-Handy-Seite aus.
// Läuft nach admin.js; ändert nur die Navigation, die Seiten selbst liegen unter /static/docker/.
(function () {
  let lang = "de";
  const L = { de: { group: "Docker", setup: "Einrichtung", pair: "Gerät koppeln" }, en: { group: "Docker", setup: "Setup", pair: "Pair device" } };

  function addNav() {
    const nav = document.getElementById("nav");
    if (!nav || !nav.children.length || nav.querySelector("[data-docker]")) return;
    const handy = nav.querySelector('button[data-view="handy"]');
    if (handy) handy.hidden = true;
    const t = L[lang];
    const g = document.createElement("div"); g.className = "nav-group"; g.textContent = t.group; g.dataset.docker = "1";
    nav.appendChild(g);
    for (const [href, label] of [["/static/docker/koppeln.html", t.pair], ["/static/docker/einrichtung.html", t.setup]]) {
      const b = document.createElement("button"); b.type = "button"; b.dataset.docker = "1";
      b.innerHTML = '<span class="ico" aria-hidden="true">◈</span>'; b.append(document.createTextNode(label));
      b.addEventListener("click", () => { location.href = href; });
      nav.appendChild(b);
    }
  }

  async function check() {
    try {
      const r = await fetch("/api/setup", { cache: "no-store" });
      if (!r.ok) return false;              // noch nicht angemeldet
      const s = await r.json();
      lang = s.lang === "en" ? "en" : "de";
      addNav();
      if (!s.done && !sessionStorage.getItem("jl.setupSkipped")) location.href = "/static/docker/einrichtung.html";
      return true;
    } catch (e) { return false; }
  }
  // Nach dem Login baut admin.js die Navigation; so lange beobachten
  const mo = new MutationObserver(() => { if (document.getElementById("nav")?.children.length) check().then((ok) => ok && mo.disconnect()); });
  mo.observe(document.body, { childList: true, subtree: true });
  check();
})();
