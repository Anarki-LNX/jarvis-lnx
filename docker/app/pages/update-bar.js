// NuOrb (Docker): Versionszeile oben auf jeder Admin-Seite. Servername, „Auf Update prüfen“, Hinweis bei neuer Version,
// „Jetzt aktualisieren“ (mit Update-Hilfe auf dem Rechner) oder der passende Befehl zum Kopieren, Fortschritt und Ergebnis.
// Ausgabe nur über textContent, Ereignisse nur über addEventListener (CSP ohne Inline).
window.NuUpdate = (function () {
  const T = {
    de: { check: "Auf Update prüfen", checking: "Prüfe …", current: "Aktuell.", newer: "Update verfügbar: {v}", notes: "Versionshinweise",
          failed: "Prüfung fehlgeschlagen.", now: "Jetzt aktualisieren", copy: "Befehl kopieren", copied: "Kopiert.",
          sure: "NuOrb wird auf {v} aktualisiert. Vorher werden Einstellungen und Daten gesichert. Der Container startet dabei neu, das dauert einige Minuten. Fortfahren?",
          running: "Update auf {v} läuft. Die Seite lädt danach neu.", done: "Aktualisiert auf {v}.",
          waiting: "Update auf {v} angefordert, warte auf die Update-Hilfe …",
          rolled: "Das Update auf {v} ist nicht sauber gestartet. NuOrb ist zurück auf der vorigen Version, mit den Daten von vorher.",
          fail: "Das Update ist fehlgeschlagen: {m}", back: "Zurück zur vorigen Version:",
          cmdDocker: "Auf dem Rechner mit NuOrb ausführen:", cmdProxmox: "Im Proxmox-Container ausführen (auf dem Host: pct enter <ID>):" },
    en: { check: "Check for updates", checking: "Checking …", current: "Up to date.", newer: "Update available: {v}", notes: "Release notes",
          failed: "Check failed.", now: "Update now", copy: "Copy command", copied: "Copied.",
          sure: "NuOrb will be updated to {v}. Settings and data are saved first. The container restarts, this takes a few minutes. Continue?",
          running: "Update to {v} is running. The page reloads afterwards.", done: "Updated to {v}.",
          waiting: "Update to {v} requested, waiting for the update helper …",
          rolled: "The update to {v} did not start cleanly. NuOrb is back on the previous version, with the data from before.",
          fail: "The update failed: {m}", back: "Back to the previous version:",
          cmdDocker: "Run on the machine with NuOrb:", cmdProxmox: "Run inside the Proxmox container (on the host: pct enter <ID>):" },
  };
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };

  async function api(lang, body) {
    const opt = body === undefined ? { cache: "no-store", headers: { "X-UI-Lang": lang } }
      : { method: "POST", headers: { "Content-Type": "application/json", "X-NuOrb": "1", "X-UI-Lang": lang }, body: JSON.stringify(body) };
    const r = await fetch("/api/update", opt);
    const d = await r.json().catch(() => ({}));
    if (!r.ok) { const e = new Error(d.detail || r.status); e.status = r.status; throw e; }
    return d;
  }

  function commandBox(t, label, cmd) {
    const box = el("div", "ver-cmd");
    box.append(el("span", "", label + " "), el("code", "", cmd));
    const b = el("button", "btn ghost small", t.copy); b.type = "button";
    b.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(cmd); b.textContent = t.copied; } catch (e) { b.textContent = cmd; }
    });
    box.append(" ", b);
    return box;
  }

  function mount(bar, langFn) {
    let poll = null, wasRunning = false;
    const render = (st, justChecked) => {
      const t = T[langFn()] || T.en;
      bar.replaceChildren();
      const hs = (st.helper && st.helper.status) || null;
      const waiting = !!st.pending;                       // angefordert, die Hilfe hat noch nicht geantwortet
      const running = (hs && hs.state === "running") || waiting;
      bar.classList.toggle("newer", !!st.newer || running);
      bar.append(el("span", "ver-label", st.label || ""));
      if (st.enabled && !running) {
        const b = el("button", "btn ghost small", t.check); b.type = "button";
        b.addEventListener("click", async () => {
          b.disabled = true; b.textContent = t.checking;
          try { render(await api(langFn(), { check: true }), true); } catch (e) { b.disabled = false; b.textContent = t.check; }
        });
        bar.append(b);
      }
      const s = el("span", "ver-status");
      if (waiting && !(hs && hs.state === "running")) {
        s.textContent = t.waiting.replace("{v}", st.pending.release || "");
        wasRunning = true;
      } else if (running) {
        s.textContent = t.running.replace("{v}", hs.release || "");
        wasRunning = true;
      } else if (st.newer) {
        s.append(el("strong", "", t.newer.replace("{v}", st.latest)));
        if (st.url) { const a = el("a", "", t.notes); a.href = st.url; a.target = "_blank"; a.rel = "noopener noreferrer"; s.append(" ", a); }
      } else if (st.error) s.textContent = t.failed;
      else if (justChecked) s.textContent = t.current;
      if (s.childNodes.length) bar.append(s);
      if (st.newer && !running) {
        if (st.helper) {
          const u = el("button", "btn small primary", t.now); u.type = "button";
          u.addEventListener("click", async () => {
            if (!confirm(t.sure.replace("{v}", st.latest))) return;
            u.disabled = true;
            try { render(await api(langFn(), { update: st.latest })); startPoll(); }
            catch (e) { u.disabled = false; bar.append(el("span", "ver-status", String(e.message || e))); }
          });
          bar.append(u);
        } else {
          bar.append(commandBox(t, st.kind === "proxmox" ? t.cmdProxmox : t.cmdDocker, (st.commands || {}).update || ""));
        }
      }
      const recent = hs && Date.now() - Date.parse(hs.time || 0) < 86400000;   // Fehlerhinweise nur einen Tag lang
      if (hs && !running && recent) {
        if (hs.state === "done" && wasRunning) { bar.append(el("span", "ver-status", t.done.replace("{v}", hs.release))); setTimeout(() => location.reload(), 3000); }
        if (hs.state === "rolled_back") bar.append(el("div", "ver-note", t.rolled.replace("{v}", hs.release)));
        if (hs.state === "failed") {
          bar.append(el("div", "ver-note", t.fail.replace("{m}", hs.message || "")));
          bar.append(commandBox(t, t.back, (st.commands || {}).rollback || ""));
        }
      }
      if (running) startPoll(); else stopPoll();
    };
    let firstWait = true;
    const load = async () => {
      try {
        const st = await api(langFn());
        render(st);
        // allererste automatische Prüfung läuft im Hintergrund: Ergebnis gleich nachladen, damit der Hinweis sofort erscheint
        if (firstWait && st.enabled && st.auto && !st.checked) { firstWait = false; setTimeout(load, 4000); }
      } catch (e) { /* Container startet gerade neu: weiter warten */ }
    };
    function startPoll() { if (!poll) poll = setInterval(load, 5000); }
    function stopPoll() { if (poll) { clearInterval(poll); poll = null; } }
    load();
    return { reload: load };
  }
  return { mount };
})();
