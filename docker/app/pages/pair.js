// NuOrb: Browser-Kopplung. Code aus dem Admin-Panel (oder ?code= aus dem QR-Link) -> /api/pair -> Cookie -> Oberfläche.
(function () {
  const $ = (id) => document.getElementById(id);
  const T = {
    de: { lead: "Dieses Gerät ist noch nicht gekoppelt. Öffne im Admin-Panel „Gerät koppeln“ und gib den Code ein – oder scanne dort den QR-Code.",
          go: "Koppeln", hint: "Der Code gilt 10 Minuten und nur einmal.", bad: "Code falsch oder abgelaufen.", many: "Zu viele Versuche. Bitte 15 Minuten warten.",
          net: "Keine Verbindung zum Server.", busy: "Kopple …" },
    en: { lead: "This device is not paired yet. Open “Pair device” in the admin panel and enter the code – or scan the QR code there.",
          go: "Pair", hint: "The code is valid for 10 minutes and only once.", bad: "Wrong or expired code.", many: "Too many attempts. Please wait 15 minutes.",
          net: "No connection to the server.", busy: "Pairing …" },
  };
  let t = T.de;
  fetch("/api/info", { cache: "no-store" }).then((r) => r.json()).then((i) => {
    if (i.lang === "en") { t = T.en; document.documentElement.lang = "en"; }
    $("lead").textContent = t.lead; $("go").textContent = t.go; $("hint").textContent = t.hint;
    if (i.brand) document.querySelector("h1").textContent = i.brand;
    if (i.name) document.title = i.name + " · " + t.go;
    if (i.paired) location.replace("/");
  }).catch(() => {});

  async function pair(code) {
    $("err").textContent = ""; $("go").disabled = true; $("go").textContent = t.busy;
    try {
      const r = await fetch("/api/pair", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code, device: navigator.userAgent.replace(/\(.*?\)/g, "").trim().slice(0, 60) || "Browser",
                               platform: "web", cookie: true }) });
      if (r.ok) { history.replaceState(null, "", "/"); location.replace("/"); return; }
      $("err").textContent = r.status === 429 ? t.many : t.bad;
    } catch (e) { $("err").textContent = t.net; }
    $("go").disabled = false; $("go").textContent = t.go;
  }
  $("f").addEventListener("submit", (e) => { e.preventDefault(); pair($("code").value.trim()); });
  const qp = new URLSearchParams(location.search);
  if (qp.get("code")) { $("code").value = qp.get("code"); pair(qp.get("code")); }
})();
