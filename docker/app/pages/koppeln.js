// NuOrb (Docker): „Gerät koppeln“ – Einmal-Code + QR (nuorb://pair?…), Geräteliste mit Entkoppeln.
(function () {
  const $ = (id) => document.getElementById(id);
  const EN = {
    back: "← Back to admin", title: "Pair device", lead: "Connect the NuOrb app or a browser to this server. The code is valid for 10 minutes and only once.",
    new: "Create new pairing code", cap_app: "App: scan the QR code", code_lbl: "Code", manual: "Or enter manually in the app:",
    fp_lbl: "Certificate fingerprint (SHA-256 of the home CA)", browser: "Pair a browser instead of the app", h_dev: "Paired devices",
    th_name: "Name", th_kind: "Type", th_seen: "Last seen", off: "Pairing is not required (NUORB_REQUIRE_PAIRING=0): the UI is reachable from the whole LAN without pairing.",
    h_sec: "Security", sec: "Do not expose ports 8443/8444 to the internet. When away: use a VPN (e.g. WireGuard or Tailscale) into your home network. Unpair a device here if you lose it.",
  };
  const M = {
    de: { left: (s) => `noch ${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")} min gültig`, expired: "abgelaufen", revoke: "Entkoppeln",
          sure: "Gerät wirklich entkoppeln?", none: "Noch keine Geräte gekoppelt.", noFp: "eigenes Zertifikat – kein Fingerabdruck nötig",
          cert: (h, n) => `Achtung: Das Zertifikat gilt nicht für „${h}“ (nur ${n}). Trage die Adresse in NUORB_HOSTS in der .env ein und starte den Container neu.` },
    en: { left: (s) => `valid for ${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")} min`, expired: "expired", revoke: "Unpair",
          sure: "Really unpair this device?", none: "No devices paired yet.", noFp: "own certificate – no fingerprint needed",
          cert: (h, n) => `Warning: the certificate does not cover “${h}” (only ${n}). Add the address to NUORB_HOSTS in .env and restart the container.` },
  };
  let m = M.de, timer = null;
  const api = async (path, body) => {
    const r = await fetch(path, body === undefined ? { cache: "no-store" } : {
      method: "POST", headers: { "Content-Type": "application/json", "X-NuOrb": "1" }, body: JSON.stringify(body) });
    if (r.status === 401) { location.href = "/"; throw new Error("login"); }
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.detail || r.status);
    return d;
  };

  async function devices() {
    const d = await api("/api/pairing/devices");
    $("pairingOff").hidden = d.pairing_required;
    const tb = $("devs"); tb.replaceChildren();
    if (!d.devices.length) { const tr = tb.insertRow(); const td = tr.insertCell(); td.colSpan = 4; td.className = "muted"; td.textContent = m.none; }
    for (const x of d.devices) {
      const tr = tb.insertRow();
      tr.insertCell().textContent = x.name; tr.insertCell().textContent = x.platform;
      tr.insertCell().textContent = (x.last_seen || "").replace("T", " ").slice(0, 16) + (x.ip ? " · " + x.ip : "");
      const b = document.createElement("button"); b.className = "btn"; b.textContent = m.revoke;
      b.addEventListener("click", async () => { if (confirm(m.sure)) { await api("/api/pairing/revoke", { id: x.id }); devices(); } });
      tr.insertCell().append(b);
    }
  }

  $("new").addEventListener("click", async () => {
    const d = await api("/api/pairing/new", {});
    $("out").hidden = false;
    $("qr").src = d.qr; $("qrb").src = d.qr_browser;
    $("code").textContent = d.code; $("url").textContent = d.url; $("burl").textContent = d.browser_url;
    $("fp").textContent = d.fingerprint ? d.fingerprint.match(/.{2}/g).join(":") : m.noFp;
    const host = new URL(d.url).hostname;
    $("certWarn").hidden = d.host_in_cert; $("certWarn").textContent = d.host_in_cert ? "" : m.cert(host, (d.cert_names || []).join(", "));
    clearInterval(timer);
    timer = setInterval(() => {
      const s = Math.max(0, Math.round(d.expires - Date.now() / 1000));
      $("left").textContent = s ? m.left(s) : m.expired;
      if (!s) { clearInterval(timer); $("qr").style.opacity = ".15"; }
      if (s % 5 === 0) devices();
    }, 1000);
  });

  api("/api/setup").then((s) => {
    if (s.lang === "en") {
      m = M.en; document.documentElement.lang = "en"; document.title = "NuOrb · Pair device";
      document.querySelectorAll("[data-t]").forEach((el) => { if (EN[el.dataset.t]) el.textContent = EN[el.dataset.t]; });
    }
    devices();
  }).catch(() => {});
})();
