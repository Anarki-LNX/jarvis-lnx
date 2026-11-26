// Zentrale Werte der Website. Nichts Geheimes hier – diese Datei ist öffentlich.

export const SITE_URL = "https://nuorb.loopout.tech";

export const GITHUB = {
  repo: "https://github.com/Anarki-LNX/nuorb",
  issues: "https://github.com/Anarki-LNX/nuorb/issues",
  pulls: "https://github.com/Anarki-LNX/nuorb/pulls",
  releases: "https://github.com/Anarki-LNX/nuorb/releases",
  install: "https://github.com/Anarki-LNX/nuorb/blob/main/INSTALL.md",
  installDe: "https://github.com/Anarki-LNX/nuorb/blob/main/INSTALL.de.md",
  docker: "https://github.com/Anarki-LNX/nuorb/blob/main/docker/README.md",
  contributing: "https://github.com/Anarki-LNX/nuorb/blob/main/CONTRIBUTING.md",
  aiDeclaration: "https://github.com/Anarki-LNX/nuorb/blob/main/AI_DECLARATION.md",
  license: "https://github.com/Anarki-LNX/nuorb/blob/main/LICENSE",
  nixos: "https://github.com/Anarki-LNX/nuorb/blob/main/nixos/README.md",
  api: "https://api.github.com/repos/Anarki-LNX/nuorb",
};

export const INSTALL_CMD = "curl -fsSL https://raw.githubusercontent.com/Anarki-LNX/nuorb/main/install.sh | bash";
export const INSTALL_CMD_DE = INSTALL_CMD + " -s -- --lang de";

// Öffentliche YouTube-Videos – nur verlinkt, nie eingebettet (keine Dritt-Embeds, kein Tracking).
export const YOUTUBE = {
  trailer: "https://www.youtube.com/watch?v=YxfGbj-deVI",
  tutorialEn: "https://youtu.be/NO66dwKtCvg",
  tutorialDe: "https://youtu.be/xUsvfRHpvc8",
};

/**
 * PayPal-Spendenlink – vom Nutzer bereitgestellt am 26.11.2026 (über die Koordination). Genau so übernehmen, ohne
 * Tracking-Parameter. Erlaubt sind nur https://www.paypal.com/…, https://paypal.me/… und https://www.paypal.me/… (Prüfung im Build).
 */
export const PAYPAL_URL: string | null = "https://www.paypal.me/HenryMeinekat";
export const validPaypal = (u: string | null): u is string => !!u && /^https:\/\/(www\.paypal\.com|(www\.)?paypal\.me)\/[\w\-./]+$/.test(u);

// Impressum (§ 5 DDG). NUR der Betreiber trägt diese Angaben selbst ein – nichts erfinden, nichts aus anderen Quellen
// übernehmen. Solange ein Wert mit "[" beginnt, gilt er als Platzhalter: die Seite zeigt ihn sichtbar markiert, und
// ein Release-Build (NUORB_RELEASE=1, deploy/ausrollen.sh) bricht ab.
export const IMPRINT = {
  name: "[Vor- und Nachname – vom Betreiber einzutragen]",
  street: "[Straße und Hausnummer – vom Betreiber einzutragen]",
  city: "[PLZ und Ort – vom Betreiber einzutragen]",
  country: "Deutschland",
  email: "[E-Mail-Adresse – vom Betreiber einzutragen]",
  // optional, nach § 18 Abs. 2 MStV nur bei journalistisch-redaktionellen Inhalten nötig; leer lassen = nicht angezeigt
  editorial: "",
};
export const isPlaceholder = (v: string) => v.trim().startsWith("[");
export const imprintComplete = () => !Object.entries(IMPRINT).some(([k, v]) => k !== "editorial" && (!v || isPlaceholder(v)));

// Lizenzen der Drittkomponenten (Repo, gepflegt von der Docker-Sitzung)
export const THIRD_PARTY = "https://github.com/Anarki-LNX/nuorb/blob/main/THIRD_PARTY_LICENSES.md";
