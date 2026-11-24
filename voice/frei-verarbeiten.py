#!/usr/bin/env python3
"""XIAOMI REBIRTH / NuOrb: freie Erzaehl-Aufnahmen zu Trainings-Clips verarbeiten (laeuft auf dem PC).

  python3 frei-verarbeiten.py pruefe [datei.wav]   Pegel/Rauschen/Pausen einer Aufnahme (Standard: neueste)
  python3 frei-verarbeiten.py segmente             frei/*.wav -> frei-clips/<aufnahme>_<nnn>.wav (3–12 s, an Pausen)
  python3 frei-verarbeiten.py transkribiere        neue Clips auf nuorb mit Parakeet (CPU) transkribieren
  python3 frei-verarbeiten.py alles                segmente + transkribiere
Danach:  python3 aufnahme.py export --rate 22050  (nimmt gelesene Saetze UND freie Clips zusammen)

Ergebnis in frei-clips/:
  transkript.tsv               id<TAB>text<TAB>dauer<TAB>hinweis  -> geht in den Export
  transkript-ausgeschlossen.tsv  Clips mit Problemen (harter Schnitt, Rand, Sprechtempo) -> nicht im Export.
  Bitte transkript.tsv einmal durchlesen: Text muss EXAKT dem Gesagten entsprechen (auch "aeh", Wiederholungen).
  Falsche Zeilen korrigieren oder loeschen; geloeschte Zeilen werden nicht neu transkribiert
  (dafuer die id aus transkript-ausgeschlossen.tsv entfernen bzw. Clip loeschen).
Audio geht nur ins LAN (nuorb, NUORB_SERVER_IP) und wird dort danach sofort geloescht.
"""
import json
import os
import subprocess
import sys
import tempfile

import numpy as np
import soundfile as sf

HIER = os.path.dirname(os.path.abspath(__file__))
FREI = os.environ.get("STIMME_FREI", os.path.join(HIER, "frei"))  # Umgebungsvariablen nur fuer Tests
CLIPS = os.environ.get("STIMME_CLIPS", os.path.join(HIER, "frei-clips"))
TRANSKRIPT = os.path.join(CLIPS, "transkript.tsv")
AUSGESCHLOSSEN = os.path.join(CLIPS, "transkript-ausgeschlossen.tsv")
NUORB_SERVER_IP = os.environ.get("NUORB_SERVER_IP", "nuorb.local")
NuOrb = ["ssh", "-i", os.path.expanduser("~/.ssh/id_ed25519_nuorb"), "-o", "BatchMode=yes", "root@" + NUORB_SERVER_IP]
MIN_S, MAX_S, PAUSE_S, RAND_S = 3.0, 12.0, 0.25, 0.2
FR = 0.02  # Rahmen 20 ms


def db(x):
    return 20 * np.log10(np.maximum(x, 1e-9))


def lade(pfad):
    a, r = sf.read(pfad, dtype="float32", always_2d=True)
    return a.mean(axis=1), r


def rahmen_db(a, r):
    n = int(FR * r)
    k = len(a) // n
    return db(np.sqrt(np.mean(a[: k * n].reshape(k, n) ** 2, axis=1))), n


def sprache_maske(e):
    boden = np.percentile(e, 10)
    oben = np.percentile(e, 95)
    schwelle = boden + max(10.0, 0.3 * (oben - boden))
    m = e > schwelle
    # Glaetten: kurze Luecken (< 0,1 s) in Sprache fuellen, Einzelrahmen-Knackser entfernen
    for i in range(1, len(m) - 5):
        if not m[i] and m[i - 1] and m[i: i + 5].any():
            m[i] = True
    for i in range(1, len(m) - 1):
        if m[i] and not m[i - 1] and not m[i + 1]:
            m[i] = False
    return m, boden, oben, schwelle


def bereiche(m):
    """Sprachbereiche als (start, ende) in Rahmen."""
    out, s = [], None
    for i, v in enumerate(m):
        if v and s is None:
            s = i
        elif not v and s is not None:
            out.append((s, i)); s = None
    if s is not None:
        out.append((s, len(m)))
    return out


# ---------------------------------------------------------------- Pruefung
def pruefe(pfad=None):
    if pfad is None:
        dateien = sorted(f for f in os.listdir(FREI) if f.endswith(".wav")) if os.path.isdir(FREI) else []
        if not dateien:
            print("Noch keine Aufnahme in", FREI); return
        pfad = os.path.join(FREI, dateien[-1])
    info = sf.info(pfad)
    a, r = lade(pfad)
    e, _ = rahmen_db(a, r)
    m, boden, oben, schwelle = sprache_maske(e)
    spitze = float(db(np.max(np.abs(a))))
    clips = int(np.sum(np.abs(a) > 0.98))
    anteil = m.mean()
    pausen = [(e2 - s2) * FR for s2, e2 in zip([b[1] for b in bereiche(m)][:-1], [b[0] for b in bereiche(m)][1:])]
    lange = sum(p >= PAUSE_S for p in pausen)
    # Brumm-Check: Energie bei 50/100 Hz im Rauschen
    maske = np.repeat(~m, int(FR * r))
    ruhe = a[: len(maske)][maske] if (~m).any() else a[:r]
    brumm = ""
    if len(ruhe) > r:
        sp = np.abs(np.fft.rfft(ruhe[: r * 4] * np.hanning(min(len(ruhe), r * 4))))
        f = np.fft.rfftfreq(min(len(ruhe), r * 4), 1 / r)
        def band(lo, hi):
            return float(np.mean(sp[(f > lo) & (f < hi)]) + 1e-12)
        netz = db(band(48, 52) / band(40, 60))  # schmale 50-Hz-Linie gegenueber Umgebung
        tief = db(band(20, 100) / band(300, 4000))
        if netz > 6:
            brumm = f"Netzbrummen 50 Hz (+{netz:.0f} dB). USB-Port/Kabel wechseln, Netzteile weg vom Mikro."
        elif tief > 10:
            brumm = (f"Tiefes Rumpeln unter 100 Hz im Hintergrund (+{tief:.0f} dB): Tritt-/Tischschall, Luefter "
                     "oder Verkehr. Mikro nicht auf den Tisch mit PC/Tastatur stellen, Spinne/Tuch darunter. "
                     "(Der Export filtert < 60 Hz, aber weniger ist besser.)")
    print(f"Datei: {os.path.basename(pfad)}  ({info.samplerate} Hz, {info.subtype}, {info.channels} Kanal)")
    print(f"Laenge {len(a)/r:.0f} s, davon Sprache {anteil*100:.0f} % (~{anteil*len(a)/r:.0f} s)")
    print(f"Spitze {spitze:.1f} dBFS, Samples am Anschlag: {clips}")
    print(f"Rauschboden {boden:.0f} dBFS, laute Sprache {oben:.0f} dBFS  -> Abstand {oben-boden:.0f} dB")
    print(f"Pausen >= {PAUSE_S} s: {lange} (gut fuer Schnitte)")
    urteil = []
    if clips > 3 or spitze > -1:
        urteil.append("UEBERSTEUERT: Eingangspegel in den Toneinstellungen (pavucontrol) runter oder etwas mehr Abstand.")
    elif spitze > -3:
        urteil.append("Knapp unter Anschlag: Eingangspegel etwas runter, Ziel Spitzen -6 dBFS.")
    elif spitze < -20:
        urteil.append("Zu leise: Eingangspegel hoch oder naeher ran (15–20 cm).")
    elif spitze < -12:
        urteil.append("Etwas leise, geht aber. Ideal Spitzen -12 bis -6 dBFS.")
    else:
        urteil.append("Pegel gut.")
    if boden > -50:
        urteil.append(f"Rauschen hoch ({boden:.0f} dBFS): Luefter/PC weiter weg, Fenster zu. Ziel < -55.")
    elif boden > -58:
        urteil.append(f"Rauschen ok ({boden:.0f} dBFS), unter -60 waere besser.")
    else:
        urteil.append(f"Rauschen sehr gut ({boden:.0f} dBFS).")
    if oben - boden < 30:
        urteil.append("Wenig Abstand Sprache/Rauschen: naeher ans Mikro, Eingangspegel anpassen.")
    if brumm:
        urteil.append(brumm)
    print("=> " + "\n=> ".join(urteil))


# ---------------------------------------------------------------- Segmentierung
def schneide(a, r):
    """Liefert Liste (start_sample, ende_sample, harter_schnitt)."""
    e, n = rahmen_db(a, r)
    m, *_ = sprache_maske(e)
    b = [x for x in bereiche(m) if (x[1] - x[0]) * FR >= 0.08]
    if not b:
        return []
    # Pausen zwischen Bereichen; nur echte Pausen (>= PAUSE_S) sind Schnittkandidaten
    gruppen, cur = [], [b[0]]
    for x in b[1:]:
        if (x[0] - cur[-1][1]) * FR < PAUSE_S:
            cur.append(x)
        else:
            gruppen.append((cur[0][0], cur[-1][1])); cur = [x]
    gruppen.append((cur[0][0], cur[-1][1]))
    # Gruppen gierig zu Clips 3–12 s zusammenfassen; lange Pause (>= 0,6 s) beendet Clip, wenn >= MIN_S
    clips, s, e_ = [], gruppen[0][0], gruppen[0][1]
    for g in gruppen[1:]:
        laenge_neu = (g[1] - s) * FR
        pause = (g[0] - e_) * FR
        if laenge_neu > MAX_S or ((e_ - s) * FR >= MIN_S and pause >= 0.6):
            clips.append((s, e_)); s = g[0]
        e_ = g[1]
    clips.append((s, e_))
    out = []
    for s, e_ in clips:
        # zu lange Stuecke ohne Pause: an leisester Stelle teilen (markiert)
        stuecke = [(s, e_, False)]
        while (stuecke[-1][1] - stuecke[-1][0]) * FR > MAX_S:
            s2, e2, _ = stuecke.pop()
            lo, hi = s2 + int(MIN_S / FR), min(e2 - int(1.0 / FR), s2 + int(MAX_S / FR))
            k = lo + int(np.argmin(e[lo:hi])) if hi > lo else s2 + int(MAX_S / FR)
            stuecke += [(s2, k, True), (k, e2, True)]
        out += stuecke
    rand = int(RAND_S / FR)
    ergebnis = []
    for i, (s, e_, hart) in enumerate(out):
        vor = out[i - 1][1] if i else 0
        nach = out[i + 1][0] if i + 1 < len(out) else len(e)
        s2 = s if hart and i and out[i - 1][2] else max(vor + (s - vor) // 2, s - rand, 0)
        e2 = e_ if hart and i + 1 < len(out) and out[i + 1][2] else min(e_ + (nach - e_) // 2, e_ + rand, len(e))
        if (e2 - s2) * FR >= 2.0:
            ergebnis.append((s2 * n, min(e2 * n, len(a)), hart))
    return ergebnis


def segmente():
    os.makedirs(CLIPS, exist_ok=True)
    if not os.path.isdir(FREI):
        print("Keine Aufnahmen in", FREI); return
    gesamt = 0
    for f in sorted(os.listdir(FREI)):
        if not f.endswith(".wav"):
            continue
        stamm = f[:-4]
        if any(c.startswith(stamm + "_") for c in os.listdir(CLIPS)):
            continue  # schon geschnitten
        a, r = lade(os.path.join(FREI, f))
        teile = schneide(a, r)
        hart = 0
        for k, (s, e, h) in enumerate(teile, 1):
            name = f"{stamm}_{k:03d}" + ("_h" if h else "")
            sf.write(os.path.join(CLIPS, name + ".wav"), a[s:e], r, subtype="PCM_24")
            hart += h
        dauer = sum(e - s for s, e, _ in teile) / r
        gesamt += dauer
        print(f"{f}: {len(teile)} Clips, {dauer/60:.1f} min" + (f" ({hart} mit hartem Schnitt, _h)" if hart else ""))
    print(f"neu geschnitten: {gesamt/60:.1f} min")


# ---------------------------------------------------------------- Transkription
def lies_ids(pfad):
    if not os.path.exists(pfad):
        return set()
    return {z.split("\t")[0] for z in open(pfad, encoding="utf-8") if z.strip() and not z.startswith("id\t")}


def transkribiere():
    bekannt = lies_ids(TRANSKRIPT) | lies_ids(AUSGESCHLOSSEN)
    neu = sorted(f for f in os.listdir(CLIPS) if f.endswith(".wav") and f[:-4] not in bekannt) if os.path.isdir(CLIPS) else []
    if not neu:
        print("Keine neuen Clips."); return
    print(f"{len(neu)} Clips -> nuorb (Parakeet, CPU) …", flush=True)
    rdir = "/tmp/frei-" + next(tempfile._get_candidate_names())
    with tempfile.TemporaryDirectory() as d:
        tar = os.path.join(d, "c.tar")
        subprocess.run(["tar", "-cf", tar, "-C", CLIPS] + neu, check=True)
        skript = os.path.join(HIER, "frei-transkribieren-nuorb.py")
        subprocess.run(NuOrb + [f"mkdir -m 700 {rdir} && chown nuorb: {rdir}"], check=True)
        subprocess.run(["scp", "-q", "-i", NuOrb[2], "-o", "BatchMode=yes", tar, skript,
                        f"root@{NUORB_SERVER_IP}:{rdir}/"], check=True)
        befehl = (f"cd {rdir} && mkdir c && tar -xf c.tar -C c && chown -R nuorb: {rdir} && "
                  f"su - nuorb -c 'nice ~/sprache/venv/bin/python -I {rdir}/frei-transkribieren-nuorb.py {rdir}/c'; "
                  f"rc=$?; rm -rf {rdir}; exit $rc")
        p = subprocess.run(NuOrb + [befehl], capture_output=True, text=True)
    if p.returncode:
        print("Fehler auf nuorb:", p.stderr[-2000:]); sys.exit(1)
    ergebnisse = [json.loads(z) for z in p.stdout.splitlines() if z.startswith("{")]
    gut, schlecht = [], []
    for x in ergebnisse:
        hinweis = []
        if x["id"].endswith("_h"):
            hinweis.append("harter Schnitt")
        if not x["text"]:
            hinweis.append("kein Text")
        else:
            tempo = len(x["text"]) / max(x["dauer"], 0.1)
            if not 6 <= tempo <= 22:
                hinweis.append(f"Tempo {tempo:.0f} Zeichen/s")
            if x["t_ende"] is not None and x["t_ende"] > x["dauer"] - 0.05:
                hinweis.append("Ende evtl. abgeschnitten")
        zeile = f"{x['id']}\t{x['text']}\t{x['dauer']:.1f}\t{', '.join(hinweis)}\n"
        (schlecht if hinweis else gut).append(zeile)
    for pfad, zeilen in ((TRANSKRIPT, gut), (AUSGESCHLOSSEN, schlecht)):
        neu_datei = not os.path.exists(pfad)
        with open(pfad, "a", encoding="utf-8") as f:
            if neu_datei:
                f.write("id\ttext\tdauer\thinweis\n")
            f.writelines(zeilen)
    min_gut = sum(float(z.split("\t")[2]) for z in gut) / 60
    print(f"{len(gut)} Clips ({min_gut:.1f} min) -> transkript.tsv, {len(schlecht)} -> transkript-ausgeschlossen.tsv")
    print("Bitte transkript.tsv durchsehen: Text muss exakt dem Gesagten entsprechen.")


if __name__ == "__main__":
    befehl = sys.argv[1] if len(sys.argv) > 1 else "pruefe"
    if befehl == "pruefe":
        pruefe(sys.argv[2] if len(sys.argv) > 2 else None)
    elif befehl == "segmente":
        segmente()
    elif befehl == "transkribiere":
        transkribiere()
    elif befehl == "alles":
        segmente(); transkribiere()
    else:
        print(__doc__)
