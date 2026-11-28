// NuOrb: Spendenkarte am Ende jeder Admin-Seite (Admin-Panel und Docker-Zusatzseiten). Eine Umsetzung für alle Seiten,
// Texte je Sprache hier (die Überschrift hat den Akzent in DE und EN an verschiedenen Stellen). Nur textContent und
// Klassen (CSP ohne Inline-Styles und Inline-Skripte), Gestaltung in donate.css.
window.NuDonate = (function () {
  const PAYPAL = "https://www.paypal.com/paypalme/HenryMeinekat";
  const GITHUB = "https://github.com/Anarki-LNX/nuorb";
  const T = {
    de: { kicker: "Unterstützen", head: ["NuOrb ", "unterstützen", ""], accent: 1,
          text: "NuOrb ist kostenlos und Open Source unter der MIT-Lizenz. Es gibt keine kostenpflichtigen Funktionen. Wenn es dir hilft, sorgt eine Spende über PayPal dafür, dass es weitergeht.",
          points: ["Keine Konten, keine kostenpflichtigen Funktionen, kein Tracking.", "Ein Stern auf GitHub, Fehlerberichte und Pull Requests helfen genauso."],
          btn: "Über PayPal spenden", note: "Freiwillig. Öffnet PayPal in einem neuen Tab. Hier findet keine Zahlung statt.", star: "Stern auf GitHub" },
    en: { kicker: "Support", head: ["Support ", "NuOrb", ""], accent: 1,
          text: "NuOrb is free and open source under the MIT license. There are no paid features. If it helps you, a donation via PayPal keeps it going.",
          points: ["No accounts, no paid features, no tracking.", "A star on GitHub, bug reports and pull requests help just as much."],
          btn: "Donate via PayPal", note: "Voluntary. Opens PayPal in a new tab. No payment happens here.", star: "Star on GitHub" },
  };
  const mk = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const deco = (text) => { const s = mk("span", "", text); s.setAttribute("aria-hidden", "true"); return s; };
  const ext = (a, href) => { a.href = href; a.target = "_blank"; a.rel = "noopener noreferrer"; return a; };

  function build(lang) {
    const t = T[lang] || T.en;
    const card = mk("aside", "donate"); card.id = "nuDonate"; card.setAttribute("aria-labelledby", "nuDonateTitle");
    card.setAttribute("data-noi18n", "");   // eigene Texte je Sprache, die Wort-Übersetzung des Panels nicht anwenden
    const tx = mk("div", "donate-text");
    const kick = mk("div", "donate-kicker"); kick.append(deco("♥ · "), mk("span", "", t.kicker));
    const h = mk("h2", "donate-title"); h.id = "nuDonateTitle";
    t.head.forEach((part, i) => { if (part) h.append(i === t.accent ? mk("em", "", part) : document.createTextNode(part)); });
    const ul = mk("ul", "donate-points");
    t.points.forEach((p) => ul.append(mk("li", "", p)));
    tx.append(kick, h, mk("p", "", t.text), ul);
    const act = mk("div", "donate-action");
    const btn = ext(mk("a", "donate-btn"), PAYPAL); btn.append(deco("♡ "), mk("span", "", t.btn), deco(" ↗"));
    const star = ext(mk("a", "donate-star"), GITHUB); star.append(deco("☆ "), mk("span", "", t.star));
    act.append(btn, mk("span", "donate-note", t.note), star);
    card.append(tx, act);
    return card;
  }

  // render(Container, Sprache): Karte am Ende des Containers anlegen oder in der neuen Sprache ersetzen
  function render(container, lang) {
    if (!container) return;
    const old = document.getElementById("nuDonate");
    const card = build(lang === "de" ? "de" : "en");
    if (old) old.replaceWith(card); else container.append(card);
  }
  // Admin-Panel: am Ende der Hauptspalte, Sprache des Panels, beim Umschalten neu
  const adminMain = () => document.querySelector("main#main.main");
  const adminLang = () => (window.I18N && window.I18N.lang) || document.documentElement.lang || "de";
  function auto() {
    const m = adminMain();
    if (!m) return;
    render(m, adminLang());
    document.addEventListener("click", (e) => {
      if (e.target.closest && e.target.closest("[data-langtoggle] button")) setTimeout(() => render(adminMain(), adminLang()), 60);
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", auto); else auto();
  return { render };
})();
