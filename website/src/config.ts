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
 * PayPal-Spendenlink. Bisher wurde KEIN offizieller Link gefunden (Repo, Historie, GitHub Pages, alle Repos geprüft).
 * Erst eintragen, wenn der Projektinhaber den Link bestätigt hat – niemals raten. Solange null, ist der Button
 * sichtbar deaktiviert. Erlaubt sind nur https://www.paypal.com/… und https://paypal.me/… (Prüfung im Build).
 */
export const PAYPAL_URL: string | null = null;
export const validPaypal = (u: string | null): u is string => !!u && /^https:\/\/(www\.paypal\.com|paypal\.me)\/[\w\-./?=&%]+$/.test(u);

// Rechtliches: Betreiber identisch mit loopout.tech – dort stehen Impressum und Kontakt (keine Kopie hier).
export const LEGAL = {
  imprintDe: "https://loopout.tech/impressum",
  imprintEn: "https://loopout.tech/en/imprint",
};
