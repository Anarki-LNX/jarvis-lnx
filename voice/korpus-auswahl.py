#!/usr/bin/env python3
"""XIAOMI REBIRTH / NuOrb: phonetisch ausgewogenen Aufnahme-Korpus erzeugen.

Quellen (alle CC0):
  - Common Voice, Deutsch: server/data/de/sentence-collector.txt und wiki.de.rerun-2022-08.txt
    (https://github.com/common-voice/common-voice/tree/main/server/data/de)
  - stimme/saetze-eigene.txt (NuOrb-typische Antworten, fuer dieses Projekt geschrieben)

Verfahren: filtern (Laenge, keine Ziffern/Abkuerzungen/Fremdwort-Schreibungen), mit espeak-ng
(ueber piper.phonemize_espeak) in Phoneme umwandeln, dann gierig die Saetze waehlen, die die meisten
noch seltenen Phoneme und Diphone (Phonem-Paare) dazubringen. Die Reihenfolge ist nach Nutzen
sortiert: wer nach 20 min aufhoert, hat trotzdem die beste Abdeckung fuer 20 min.
Jeder 8. Satz ist ein eigener NuOrb-Satz, ca. 15 % Fragen, ca. 5 % Ausrufe.

Aufruf (braucht piper-tts, z. B. Hermes-Python auf nuorb):
  python -I korpus-auswahl.py <cv-dateien...> --eigene saetze-eigene.txt --anzahl 1000 > saetze.tsv
Ausgabe: id <TAB> text <TAB> quelle <TAB> geschaetzte_sekunden <TAB> kumuliert_minuten
"""
import argparse
import heapq
import math
import random
import re
import sys
from collections import Counter

from piper.phonemize_espeak import EspeakPhonemizer

ERLAUBT = re.compile(r"^[A-ZÄÖÜ][A-Za-zÄÖÜäöüß ,.;:?!'\-]+[.?!]$")
FREMD = re.compile(r"y|q(?!u)|c(?![hk])|th|ea|ou|ae|oe(?!r)|ue(?!r)|w$|ff$|ii", re.I)
ZEICHEN_PRO_SEK = 14.0  # ruhiges Vorlesen, grob


TABU = re.compile(r"sex|geschlechts|corona|impf|nazi|hitler|tod|töte|mord|leiche|krieg|waffe|droge|selbstmord|"
                  r"porno|vergewalt|terror|jude|juden|islam|religi|partei|afd|spd|cdu|fdp", re.I)
WORTZAHL = Counter()  # Wortfrequenz ueber alle Quellen, gegen Eigennamen und Bandwurmwoerter


def woerter(s: str) -> list[str]:
    return [x.lower() for x in re.findall(r"[A-Za-zÄÖÜäöüß]+", s)]


def satz_ok(s: str) -> bool:
    w = s.split()
    if TABU.search(s) or re.search(r"[a-zäöü][A-ZÄÖÜ]", s):  # Themen / BinnenMajuskeln
        return False
    if any(WORTZAHL[x] < 3 or len(x) > 18 for x in woerter(s)):
        return False
    if not (5 <= len(w) <= 14) or not (25 <= len(s) <= 110) or not ERLAUBT.match(s):
        return False
    if re.search(r"[A-ZÄÖÜ]{2}", s):  # Abkuerzungen
        return False
    # Eigennamen/Fremdwoerter: Woerter mit untypischen Schreibungen raus
    return not any(FREMD.search(x.strip(",.;:?!'-")) for x in w)


def einheiten(ph: list[str]) -> list[str]:
    """Phoneme (ohne Betonung) und Diphone innerhalb und ueber Wortgrenzen."""
    p = [x for x in ph if x not in ("ˈ", "ˌ", ",", ".", "?", "!", ";", ":", "-")]
    toks = ["_" if x == " " else x for x in p]
    toks = ["_"] + toks + ["_"]
    uni = [t for t in toks if t != "_"]
    di = [a + "|" + b for a, b in zip(toks, toks[1:]) if not (a == "_" and b == "_")]
    return uni + di


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dateien", nargs="+")
    ap.add_argument("--eigene", required=True)
    ap.add_argument("--anzahl", type=int, default=1000)
    ap.add_argument("--pool", type=int, default=25000)
    args = ap.parse_args()

    random.seed(42)
    for f in args.dateien:
        for z in open(f, encoding="utf-8"):
            WORTZAHL.update(woerter(z))
    kand, gesehen = [], set()
    for f in args.dateien:
        quelle = "cv-" + f.split("/")[-1].split(".")[0]
        for z in open(f, encoding="utf-8"):
            s = z.strip()
            schluessel = " ".join(s.lower().split()[:3])  # Fast-Dubletten ("Sobald mir eine …")
            if satz_ok(s) and schluessel not in gesehen:
                gesehen.add(schluessel)
                kand.append((s, quelle))
    random.shuffle(kand)
    kand = kand[: args.pool]
    eigene = [z.strip() for z in open(args.eigene, encoding="utf-8") if z.strip() and not z.startswith("#")]
    print(f"Kandidaten: {len(kand)}, eigene: {len(eigene)}", file=sys.stderr)

    pho = EspeakPhonemizer()
    def zerlege(s):
        return einheiten([x for satz in pho.phonemize("de", s) for x in satz])

    E = [zerlege(s) for s in eigene]
    K = [zerlege(s) for s, _ in kand]
    zaehler = Counter()

    def gewinn(u: list[str], quelle: str) -> float:
        g = sum(1.0 / (1 + zaehler[x]) ** 1.5 for x in set(u)) / max(len(u), 1) ** 0.75
        return g * (1.0 if quelle == "cv-sentence-collector" else 0.85)

    # Lazy-Greedy: Gewinne sinken nur, also erst neu berechnen, wenn ein Kandidat oben liegt
    heap = [(-gewinn(u, kand[i][1]), i, 0) for i, u in enumerate(K)]
    heapq.heapify(heap)
    runde, auswahl, ei = 0, [], 0
    fragen = ausrufe = 0
    while len(auswahl) < args.anzahl and (heap or ei < len(eigene)):
        if (len(auswahl) + 1) % 8 == 0 and ei < len(eigene):
            auswahl.append((eigene[ei], "eigen"))
            zaehler.update(E[ei]); ei += 1; runde += 1
            continue
        while heap:
            g, i, r = heapq.heappop(heap)
            if r != runde:
                heapq.heappush(heap, (-gewinn(K[i], kand[i][1]), i, runde)); continue
            s = kand[i][0]
            # Satzart-Quoten weich steuern
            if s.endswith("?") and fragen > 0.15 * (len(auswahl) + 1):
                continue
            if s.endswith("!") and ausrufe > 0.05 * (len(auswahl) + 1):
                continue
            if s.endswith("."):
                q = (len(auswahl) + 1)
                if fragen < 0.13 * q and random.random() < 0.5:  # Fragen etwas bevorzugen
                    heapq.heappush(heap, (g * 0.7, i, runde)); continue
            fragen += s.endswith("?"); ausrufe += s.endswith("!")
            auswahl.append(kand[i]); zaehler.update(K[i]); runde += 1
            break

    alle_di = {x for u in K + E for x in u if "|" in x}
    gedeckt = {x for x in zaehler if "|" in x}
    print(f"Diphon-Abdeckung: {len(gedeckt)}/{len(alle_di)} der im Pool vorkommenden", file=sys.stderr)
    print("id\ttext\tquelle\tsek\tkum_min")
    kum = 0.0
    for n, (s, q) in enumerate(auswahl, 1):
        sek = len(s) / ZEICHEN_PRO_SEK + 0.6
        kum += sek
        print(f"{n:04d}\t{s}\t{q}\t{sek:.1f}\t{kum/60:.1f}")


if __name__ == "__main__":
    main()
