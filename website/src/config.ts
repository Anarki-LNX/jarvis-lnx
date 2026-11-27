// Zentrale Werte der Website. Nichts Geheimes hier – diese Datei ist öffentlich.

export const SITE_URL = "https://nuorb.loopout.tech";

export const GITHUB = {
  repo: "https://github.com/Anarki-LNX/nuorb",
  issues: "https://github.com/Anarki-LNX/nuorb/issues",
  pulls: "https://github.com/Anarki-LNX/nuorb/pulls",
  releases: "https://github.com/Anarki-LNX/nuorb/releases",
  releasesLatest: "https://github.com/Anarki-LNX/nuorb/releases/latest",
  proxmox: "https://github.com/Anarki-LNX/nuorb/blob/main/docs/proxmox.md",
  proxmoxDe: "https://github.com/Anarki-LNX/nuorb/blob/main/docs/proxmox.de.md",
  manual: "https://github.com/Anarki-LNX/nuorb/blob/main/INSTALL.md#6-manual-installation-alternative",
  manualDe: "https://github.com/Anarki-LNX/nuorb/blob/main/INSTALL.de.md#6-manuelle-installation-alternative",
  install: "https://github.com/Anarki-LNX/nuorb/blob/main/INSTALL.md",
  installDe: "https://github.com/Anarki-LNX/nuorb/blob/main/INSTALL.de.md",
  docker: "https://github.com/Anarki-LNX/nuorb/blob/main/docker/README.md",
  dockerHub: "https://hub.docker.com/r/anarkilnx/nuorb",
  contributing: "https://github.com/Anarki-LNX/nuorb/blob/main/CONTRIBUTING.md",
  aiDeclaration: "https://github.com/Anarki-LNX/nuorb/blob/main/AI_DECLARATION.md",
  license: "https://github.com/Anarki-LNX/nuorb/blob/main/LICENSE",
  nixos: "https://github.com/Anarki-LNX/nuorb/blob/main/nixos/README.md",
  api: "https://api.github.com/repos/Anarki-LNX/nuorb",
};

export const INSTALL_CMD = "curl -fsSL https://raw.githubusercontent.com/Anarki-LNX/nuorb/main/install.sh | bash";
export const INSTALL_CMD_DE = INSTALL_CMD + " -s -- --lang de";

// Proxmox VE: Einzeiler für die Host-Shell (Namen laut NUORB_PROXMOX_SPEC, 27.11.2026)
export const PROXMOX_CMD = 'bash -c "$(curl -fsSL https://raw.githubusercontent.com/Anarki-LNX/nuorb/main/proxmox/nuorb-lxc.sh)"';

// Docker Compose von Hand (wie INSTALL.md, Abschnitt 6), in drei kopierbaren Schritten
const RAW = "https://raw.githubusercontent.com/Anarki-LNX/nuorb/main/docker";
export const COMPOSE_CMDS = {
  fetch: `mkdir -p ~/nuorb && cd ~/nuorb\ncurl -fsSLO ${RAW}/compose.yaml\ncurl -fsSL ${RAW}/.env.example -o .env`,
  edit: "nano .env",
  start: "docker compose up -d\ndocker compose logs -f nuorb",
};

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

// Rechtliches: gleicher Betreiber wie loopout.tech. Das dortige Impressum (§ 5 DDG, § 18 Abs. 2 MStV) deckt diese
// Subdomain ab (geprüft von der Koordination am 26.11.2026) – nur verlinken, keine Personendaten kopieren.
export const LEGAL = {
  imprintDe: "https://loopout.tech/impressum",
  imprintEn: "https://loopout.tech/en/imprint",
};

// Lizenzen der Drittkomponenten (Repo, gepflegt von der Docker-Sitzung)
export const THIRD_PARTY = "https://github.com/Anarki-LNX/nuorb/blob/main/THIRD_PARTY_LICENSES.md";
