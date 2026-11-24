#!/usr/bin/env python3
"""XIAOMI REBIRTH / NuOrb: Aufnahmewerkzeug fuer die eigene Stimme (laeuft auf dem PC).

  python3 aufnahme.py                  Aufnehmen (Fenster). Saetze aus saetze.tsv, Ablage in aufnahmen/
  python3 aufnahme.py export --rate 22050   Trainingsdaten bauen: export-22050/wavs/*.wav + metadata.csv
                                       (gelesene Saetze + freie Clips aus frei-clips/, falls transkribiert)
  python3 aufnahme.py selbsttest       Pruefung ohne Mikrofon (synthetische Daten)

Tasten:  Leertaste = Aufnahme starten/stoppen (stoppen speichert sofort)
         Enter / Pfeil rechts = naechster Satz     Pfeil links = vorheriger Satz
         P = anhoeren    S = ueberspringen    R = nochmal aufnehmen (wie Leertaste)
Aufnahme: mono, 48 kHz, 24 Bit WAV (Rohdaten, nichts wird veraendert).
Der Export schneidet Stille ab, gleicht die Lautstaerke an und rechnet auf 22,05/24 kHz um.
Alles bleibt lokal; es wird nichts hochgeladen.
Braucht: numpy, sounddevice, soundfile, tkinter; fuer den Export zusaetzlich ffmpeg.
"""
import argparse
import collections
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time

import numpy as np
import soundfile as sf

HIER = os.path.dirname(os.path.abspath(__file__))
SAETZE = os.path.join(HIER, "saetze.tsv")
ZIEL = os.path.join(HIER, "aufnahmen")
RATE = 48000
VORLAUF_S = 0.3  # so viel Audio vor dem Tastendruck wird mitgenommen (Anlaute nicht abschneiden)


# ---------------------------------------------------------------- Analyse (auch ohne GUI nutzbar)
def db(x: float) -> float:
    return 20 * np.log10(max(x, 1e-9))


def analysiere(a: np.ndarray, rate: int, text: str = "") -> tuple[str, list[str]]:
    """Gibt (Ampel, Hinweise) zurueck. Ampel: ok | warnung | schlecht."""
    hinweise, stufe = [], 0
    if len(a) == 0:
        return "schlecht", ["Keine Daten."]
    dauer = len(a) / rate
    spitze = float(np.max(np.abs(a)))
    clips = int(np.sum(np.abs(a) > 0.98))
    blk = max(1, int(0.02 * rate))
    n = len(a) // blk
    rms = np.sqrt(np.mean(a[: n * blk].reshape(n, blk) ** 2, axis=1)) if n else np.array([0.0])
    rausch = db(float(np.percentile(rms, 10)))
    sprache = db(float(np.percentile(rms, 90)))
    if clips > 3:
        hinweise.append(f"Uebersteuert ({clips} Samples am Anschlag). Leiser sprechen oder Pegel runter."); stufe = 2
    elif db(spitze) > -2:
        hinweise.append("Sehr knapp am Anschlag. Pegel etwas runter."); stufe = max(stufe, 1)
    if db(spitze) < -24:
        hinweise.append(f"Zu leise (Spitze {db(spitze):.0f} dBFS). Naeher ans Mikro oder Pegel hoch."); stufe = 2
    elif db(spitze) < -15:
        hinweise.append(f"Etwas leise (Spitze {db(spitze):.0f} dBFS)."); stufe = max(stufe, 1)
    if rausch > -50:
        hinweise.append(f"Hintergrund laut ({rausch:.0f} dBFS). Ziel: unter -55."); stufe = max(stufe, 1)
    if sprache - rausch < 25:
        hinweise.append(f"Wenig Abstand Sprache/Rauschen ({sprache - rausch:.0f} dB)."); stufe = max(stufe, 1)
    if text:
        erwartet = len(text) / 14.0
        if dauer < 0.5 * erwartet:
            hinweise.append("Kuerzer als erwartet. Ganzer Satz drauf?"); stufe = max(stufe, 1)
        elif dauer > 3.0 * erwartet + 2:
            hinweise.append("Viel laenger als erwartet. Lange Pause oder Versprecher?"); stufe = max(stufe, 1)
    hinweise.insert(0, f"{dauer:.1f} s, Spitze {db(spitze):.0f} dBFS, Rauschen {rausch:.0f} dBFS")
    return ("ok", "warnung", "schlecht")[stufe], hinweise


def lade_saetze(pfad: str) -> list[tuple[str, str]]:
    zeilen = []
    with open(pfad, encoding="utf-8") as f:
        for z in f:
            teile = z.rstrip("\n").split("\t")
            if len(teile) >= 2 and teile[0] != "id":
                zeilen.append((teile[0], teile[1]))
    return zeilen


# ---------------------------------------------------------------- Export
def beschneide(a: np.ndarray, rate: int, schwelle_db=-45.0, rand_s=0.15) -> np.ndarray:
    blk = max(1, int(0.01 * rate))
    n = len(a) // blk
    if n == 0:
        return a
    rms = np.sqrt(np.mean(a[: n * blk].reshape(n, blk) ** 2, axis=1))
    schwelle = max(10 ** (schwelle_db / 20), np.percentile(rms, 10) * 3)
    aktiv = np.where(rms > schwelle)[0]
    if len(aktiv) == 0:
        return a
    s = max(0, aktiv[0] * blk - int(rand_s * rate))
    e = min(len(a), (aktiv[-1] + 1) * blk + int(rand_s * rate))
    return a[s:e]


FREI_CLIPS = os.path.join(HIER, "frei-clips")
FREI_TEXT = os.path.join(FREI_CLIPS, "transkript.tsv")  # von frei-verarbeiten.py, nach Durchsicht


def standard_quellen() -> list[tuple[str, str]]:
    q = [(ZIEL, SAETZE)]
    if os.path.exists(FREI_TEXT):
        q.append((FREI_CLIPS, FREI_TEXT))
    return q


def exportiere(ziel_rate: int, quellen=None, aus=None) -> str:
    """quellen: Liste (wav-Ordner, tsv mit id<TAB>text). Ergebnis: ein gemeinsamer Trainingsordner."""
    aus = aus or os.path.join(HIER, f"export-{ziel_rate}")
    os.makedirs(os.path.join(aus, "wavs"), exist_ok=True)
    meta, gesamt, fehlt = [], 0.0, 0
    paare = []
    for quelle, saetze in (quellen or standard_quellen()):
        if not os.path.isdir(quelle):
            continue
        texte = dict(lade_saetze(saetze))
        for name in sorted(os.listdir(quelle)):
            if name.endswith(".wav"):
                if name[:-4] in texte and texte[name[:-4]].strip():
                    paare.append((os.path.join(quelle, name), name[:-4], texte[name[:-4]]))
                else:
                    fehlt += 1
    for wav, sid, text in paare:
        a, r = sf.read(wav, dtype="float32", always_2d=True)
        a = beschneide(a.mean(axis=1), r)
        # Lautheit angleichen: Sprach-RMS auf -20 dBFS, Spitze hoechstens -1 dBFS
        blk = max(1, int(0.02 * r)); n = len(a) // blk
        rms = np.sqrt(np.mean(a[: n * blk].reshape(n, blk) ** 2, axis=1)) if n else np.array([1e-3])
        g = 10 ** (-20 / 20) / max(float(np.percentile(rms, 90)), 1e-6)
        g = min(g, 10 ** (-1 / 20) / max(float(np.max(np.abs(a))), 1e-6))
        a = (a * g).astype(np.float32)
        p = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "f32le", "-ar", str(r), "-ac", "1",
                            "-i", "pipe:0", "-af", "highpass=f=60:poles=2", "-ar", str(ziel_rate), "-ac", "1", "-c:a", "pcm_s16le", "-y",
                            os.path.join(aus, "wavs", sid + ".wav")], input=a.tobytes(), capture_output=True)
        if p.returncode:
            raise RuntimeError(p.stderr.decode())
        gesamt += len(a) / r
        meta.append((sid, text))
    with open(os.path.join(aus, "metadata.csv"), "w", encoding="utf-8") as f:  # LJSpeech/Piper: id|text
        f.writelines(f"{i}|{t}\n" for i, t in meta)
    with open(os.path.join(aus, "liste.txt"), "w", encoding="utf-8") as f:  # Pfad|Text (F5-TTS u. a.)
        f.writelines(f"wavs/{i}.wav|{t}\n" for i, t in meta)
    print(f"{len(meta)} Dateien, {gesamt/60:.1f} min nach {aus}" + (f" ({fehlt} ohne Text uebersprungen)" if fehlt else ""))
    return aus


# ---------------------------------------------------------------- GUI
def gui(args):
    import sounddevice as sd
    import tkinter as tk
    from tkinter import ttk, messagebox

    saetze = lade_saetze(args.saetze)
    os.makedirs(args.ziel, exist_ok=True)
    skip_datei = os.path.join(args.ziel, "uebersprungen.txt")
    uebersprungen = set(open(skip_datei).read().split()) if os.path.exists(skip_datei) else set()

    def pfad(i):
        return os.path.join(args.ziel, saetze[i][0] + ".wav")

    def erster_offener():
        for i, (sid, _) in enumerate(saetze):
            if not os.path.exists(pfad(i)) and sid not in uebersprungen:
                return i
        return len(saetze) - 1

    zustand = {"i": erster_offener(), "rec": False, "puffer": [], "stream": None,
               "spitze": 0.0, "halte": 0.0, "halte_t": 0.0, "rate": args.rate}
    vorlauf = collections.deque(maxlen=64)
    q_pegel = queue.Queue()

    def callback(indata, frames, t, status):
        blk = indata[:, 0].copy()
        if zustand["rec"]:
            zustand["puffer"].append(blk)
        else:
            vorlauf.append(blk)
        q_pegel.put(float(np.max(np.abs(blk))) if len(blk) else 0.0)

    def oeffne_stream(geraet):
        if zustand["stream"]:
            zustand["stream"].close()
        zustand["stream"] = sd.InputStream(device=geraet, channels=1, samplerate=zustand["rate"],
                                           dtype="float32", blocksize=1024, callback=callback)
        zustand["stream"].start()

    # --- Fenster
    root = tk.Tk()
    root.title("NuOrb – Stimmaufnahme")
    root.geometry("1100x620")
    stil = ttk.Style(); stil.configure("TButton", font=("Sans", 12))
    oben = ttk.Frame(root, padding=10); oben.pack(fill="x")
    lbl_fort = ttk.Label(oben, font=("Sans", 12)); lbl_fort.pack(side="left")
    eingaenge = [(i, d["name"]) for i, d in enumerate(sd.query_devices()) if d["max_input_channels"] > 0]
    namen = [f"{i}: {n}" for i, n in eingaenge]
    try:
        std = sd.default.device[0]
    except Exception:
        std = None
    var_geraet = tk.StringVar(value=next((x for x in namen if x.startswith(f"{args.geraet if args.geraet is not None else std}:")), namen[0] if namen else ""))
    cb = ttk.Combobox(oben, textvariable=var_geraet, values=namen, width=48, state="readonly"); cb.pack(side="right")
    ttk.Label(oben, text="Mikrofon:").pack(side="right", padx=6)

    lbl_id = ttk.Label(root, font=("Sans", 11), foreground="#777"); lbl_id.pack(anchor="w", padx=14)
    lbl_satz = tk.Label(root, font=("Sans", 26), wraplength=1040, justify="center", height=4)
    lbl_satz.pack(fill="x", padx=20, pady=10)

    can = tk.Canvas(root, height=34, bg="#222", highlightthickness=0); can.pack(fill="x", padx=20)
    lbl_pegel = ttk.Label(root, font=("Sans", 10)); lbl_pegel.pack(anchor="e", padx=20)

    knoepfe = ttk.Frame(root, padding=10); knoepfe.pack()
    lbl_status = tk.Label(root, font=("Sans", 12), justify="left", anchor="w"); lbl_status.pack(fill="x", padx=20, pady=6)
    lbl_hilfe = ttk.Label(root, foreground="#777", text=(
        "Leertaste: Aufnahme an/aus (aus = gespeichert)   Enter/→: weiter   ←: zurück   P: anhören   S: überspringen\n"
        "Vor dem Sprechen kurz still sein, nach dem Satz eine halbe Sekunde warten, dann Leertaste."))
    lbl_hilfe.pack(side="bottom", pady=8)

    def minuten():
        s = 0.0
        for i in range(len(saetze)):
            if os.path.exists(pfad(i)):
                try:
                    s += sf.info(pfad(i)).duration
                except Exception:
                    pass
        return s / 60

    def zeige(status=None, farbe="#444"):
        i = zustand["i"]; sid, text = saetze[i]
        fertig = sum(os.path.exists(pfad(k)) for k in range(len(saetze)))
        lbl_fort.config(text=f"Satz {i+1} / {len(saetze)}   ·   aufgenommen: {fertig}   ·   {minuten():.1f} min")
        da = os.path.exists(pfad(i))
        lbl_id.config(text=f"#{sid}" + ("   ✔ vorhanden" if da else "") + ("   (übersprungen)" if sid in uebersprungen else ""))
        lbl_satz.config(text=text, fg="#b00" if zustand["rec"] else "#111")
        if status is not None:
            lbl_status.config(text=status, fg=farbe)
        elif not zustand["rec"]:
            lbl_status.config(text="Bereit. Leertaste zum Aufnehmen." if not da else "Schon aufgenommen. P = anhören, Leertaste = neu aufnehmen.", fg="#444")
        btn_rec.config(text="■ Stopp (Leertaste)" if zustand["rec"] else "● Aufnehmen (Leertaste)")

    def aufnahme_umschalten(_=None):
        if not zustand["rec"]:
            zustand["puffer"] = list(vorlauf)[-max(1, int(VORLAUF_S * zustand["rate"] / 1024)):]
            zustand["rec"] = True
            zeige("● Aufnahme läuft … Satz vorlesen, dann Leertaste.", "#b00")
            return
        zustand["rec"] = False
        time.sleep(0.05)
        a = np.concatenate(zustand["puffer"]) if zustand["puffer"] else np.zeros(0, np.float32)
        sid, text = saetze[zustand["i"]]
        ampel, hinweise = analysiere(a, zustand["rate"], text)
        if len(a) < 0.4 * zustand["rate"]:
            zeige("Zu kurz, nicht gespeichert.", "#b00"); return
        sf.write(pfad(zustand["i"]), a, zustand["rate"], subtype="PCM_24")
        if sid in uebersprungen:
            uebersprungen.discard(sid); speichere_skip()
        farbe = {"ok": "#070", "warnung": "#a60", "schlecht": "#b00"}[ampel]
        kopf = {"ok": "✔ Gespeichert.", "warnung": "✔ Gespeichert, aber prüfen:", "schlecht": "✖ Gespeichert, bitte neu aufnehmen:"}[ampel]
        zeige(kopf + "  " + "  ·  ".join(hinweise), farbe)

    def anhoeren(_=None):
        if zustand["rec"] or not os.path.exists(pfad(zustand["i"])):
            return
        a, r = sf.read(pfad(zustand["i"]), dtype="float32")
        threading.Thread(target=lambda: (sd.play(a, r), sd.wait()), daemon=True).start()

    def gehe(delta):
        if zustand["rec"]:
            aufnahme_umschalten()
        zustand["i"] = min(max(0, zustand["i"] + delta), len(saetze) - 1)
        zeige()

    def speichere_skip():
        with open(skip_datei, "w") as f:
            f.write("\n".join(sorted(uebersprungen)))

    def ueberspringen(_=None):
        uebersprungen.add(saetze[zustand["i"]][0]); speichere_skip(); gehe(1)

    def rauschen_messen():
        if zustand["rec"]:
            return
        zeige("Raum-Messung: 5 Sekunden still sein …", "#a60")
        zustand["puffer"] = []; zustand["rec"] = True

        def fertig():
            zustand["rec"] = False
            a = np.concatenate(zustand["puffer"]) if zustand["puffer"] else np.zeros(1, np.float32)
            r = db(float(np.sqrt(np.mean(a ** 2))))
            urteil = "sehr gut" if r < -60 else "ok" if r < -50 else "zu laut: Geräte aus, Fenster zu, Teppiche/Vorhänge helfen"
            zeige(f"Raumrauschen: {r:.0f} dBFS ({urteil}). Ziel: unter -55 dBFS.", "#070" if r < -50 else "#b00")
        root.after(5000, fertig)

    btn_rec = ttk.Button(knoepfe, command=aufnahme_umschalten, width=24); btn_rec.grid(row=0, column=0, padx=4)
    ttk.Button(knoepfe, text="▶ Anhören (P)", command=anhoeren).grid(row=0, column=1, padx=4)
    ttk.Button(knoepfe, text="← Zurück", command=lambda: gehe(-1)).grid(row=0, column=2, padx=4)
    ttk.Button(knoepfe, text="Weiter →", command=lambda: gehe(1)).grid(row=0, column=3, padx=4)
    ttk.Button(knoepfe, text="Überspringen (S)", command=ueberspringen).grid(row=0, column=4, padx=4)
    ttk.Button(knoepfe, text="Raumrauschen messen", command=rauschen_messen).grid(row=0, column=5, padx=4)

    root.bind("<space>", aufnahme_umschalten)
    root.bind("r", aufnahme_umschalten)
    root.bind("<Return>", lambda e: gehe(1)); root.bind("<Right>", lambda e: gehe(1))
    root.bind("<Left>", lambda e: gehe(-1))
    root.bind("p", anhoeren); root.bind("s", ueberspringen)

    def geraet_gewaehlt(_=None):
        try:
            oeffne_stream(int(var_geraet.get().split(":")[0]))
            zeige(f"Mikrofon: {var_geraet.get()}")
        except Exception as e:
            zeige(f"Mikrofon geht nicht: {e}", "#b00")
    cb.bind("<<ComboboxSelected>>", geraet_gewaehlt)

    def pegel_zeichnen():
        spitze = 0.0
        while not q_pegel.empty():
            spitze = max(spitze, q_pegel.get_nowait())
        zustand["spitze"] = max(spitze, zustand["spitze"] * 0.85)
        jetzt = time.monotonic()
        if spitze >= zustand["halte"] or jetzt - zustand["halte_t"] > 1.5:
            zustand["halte"], zustand["halte_t"] = spitze, jetzt
        w = can.winfo_width() or 1000
        def x(v):
            return int(w * min(1.0, max(0.0, (db(v) + 60) / 60)))
        can.delete("all")
        v =zustand["spitze"]
        farbe = "#2a6" if db(v) < -12 else "#db3" if db(v) < -3 else "#d33"
        can.create_rectangle(0, 0, x(v), 34, fill=farbe, width=0)
        can.create_line(x(zustand["halte"]), 0, x(zustand["halte"]), 34, fill="#fff", width=2)
        for m in (-40, -24, -12, -6, -3):  # Zielbereich fuer Sprachspitzen: -12 bis -6 dBFS
            xm = int(w * (m + 60) / 60)
            can.create_line(xm, 24, xm, 34, fill="#888")
            can.create_text(xm, 12, text=str(m), fill="#888", font=("Sans", 8))
        lbl_pegel.config(text=f"Spitze {db(zustand['halte']):.0f} dBFS   (Ziel beim Sprechen: −12 bis −6)")
        root.after(50, pegel_zeichnen)

    def schliessen():
        if zustand["rec"]:
            aufnahme_umschalten()
        if zustand["stream"]:
            zustand["stream"].close()
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", schliessen)

    if not args.ohne_mikro:
        try:
            oeffne_stream(int(var_geraet.get().split(":")[0]) if var_geraet.get() else None)
        except Exception as e:
            messagebox.showerror("Mikrofon", f"Konnte Mikrofon nicht öffnen: {e}")
    zeige()
    pegel_zeichnen()
    if args.ohne_mikro:
        root.after(1500, schliessen)
    root.mainloop()


# ---------------------------------------------------------------- Selbsttest
def selbsttest():
    r = RATE
    t = np.arange(int(2.5 * r)) / r
    stimme = (0.25 * np.sin(2 * np.pi * 180 * t) * (np.sin(2 * np.pi * 3 * t) > 0)).astype(np.float32)
    a = np.concatenate([np.random.default_rng(1).normal(0, 1e-4, r // 2).astype(np.float32), stimme,
                        np.zeros(r // 2, np.float32)])
    print("analyse gut:     ", analysiere(a, r, "Das ist ein kurzer Testsatz fuer die Pruefung."))
    print("analyse leise:   ", analysiere(a * 0.02, r, "Das ist ein kurzer Testsatz fuer die Pruefung.")[0])
    print("analyse clipping:", analysiere(np.clip(a * 8, -1, 1), r, "Das ist ein Testsatz.")[0])
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "auf"))
        with open(os.path.join(d, "s.tsv"), "w") as f:
            f.write("id\ttext\n0001\tEins zwei drei.\n0002\tVier fuenf sechs.\n")
        sf.write(os.path.join(d, "auf", "0001.wav"), a, r, subtype="PCM_24")
        sf.write(os.path.join(d, "auf", "0002.wav"), a * 0.3, r, subtype="PCM_24")
        aus = exportiere(22050, [(os.path.join(d, "auf"), os.path.join(d, "s.tsv"))], os.path.join(d, "ex"))
        for n in ("0001", "0002"):
            info = sf.info(os.path.join(aus, "wavs", n + ".wav"))
            b, _ = sf.read(os.path.join(aus, "wavs", n + ".wav"))
            print(f"export {n}: {info.samplerate} Hz {info.subtype} {info.duration:.2f} s, Spitze {db(np.max(np.abs(b))):.1f} dBFS")
        print(open(os.path.join(aus, "metadata.csv")).read().strip())
    print("Saetze:", len(lade_saetze(SAETZE)))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("befehl", nargs="?", default="aufnehmen", choices=["aufnehmen", "export", "selbsttest", "gui-test"])
    ap.add_argument("--saetze", default=SAETZE)
    ap.add_argument("--ziel", default=ZIEL, help="Ordner fuer die Roh-Aufnahmen")
    ap.add_argument("--rate", type=int, default=None, help="Aufnahme: 48000 (Standard); Export: 22050 oder 24000")
    ap.add_argument("--geraet", type=int, default=None, help="Eingabegeraet-Nummer (sonst Auswahl im Fenster)")
    args = ap.parse_args()
    if args.befehl == "export":
        exportiere(args.rate or 22050, [(args.ziel, args.saetze)] + standard_quellen()[1:])
    elif args.befehl == "selbsttest":
        selbsttest()
    else:
        args.rate = args.rate or RATE
        args.ohne_mikro = args.befehl == "gui-test"
        if args.ohne_mikro:
            args.ziel = tempfile.mkdtemp()
        gui(args)


if __name__ == "__main__":
    sys.exit(main())
