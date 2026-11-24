# Eigene Stimme für NuOrb – Vorbereitung (Stand 2026-11-24)

Status: vorbereitet, **noch nichts installiert oder trainiert**.
- Das früher genutzte Projekt ist nicht erreichbar (liegt auf einem entfernten PC).
- Die Auswahl unten ist daher eine eigene Entscheidung anhand des Vergleichs.
- Vor dem Start braucht es nur noch das Ok des Nutzers für Downloads und GPU-Training (Größen nennen wir dann).

## Inhalt dieses Ordners

| Datei | Zweck |
|---|---|
| `aufnahme.py` | Aufnahmewerkzeug für den PC: Satz anzeigen, aufnehmen, anhören, weiter. Pegelanzeige, Qualitätsprüfung, Export |
| `saetze.tsv` | 1000 Sätze, nach Nutzen sortiert (geschätzt: 250 ≈ 18 min, 500 ≈ 36 min, 750 ≈ 54 min, 1000 ≈ 73 min) |
| `saetze-eigene.txt` | 89 NuOrb-typische Sätze (Uhrzeiten, Zahlen, Wetter, Rückfragen), jeder 8. Satz im Korpus |
| `frei-aufnehmen.sh` | freies Erzählen am AT2020USB+ aufnehmen → `frei/` |
| `frei-verarbeiten.py` | freie Aufnahmen prüfen, an Pausen schneiden, auf nuorb transkribieren → `frei-clips/` |
| `frei-transkribieren-nuorb.py` | Hilfsskript, läuft per ssh auf nuorb (Parakeet, CPU) |
| `korpus-auswahl.py` | Erzeugt `saetze.tsv` (läuft auf nuorb, nutzt den espeak-Phonemizer von Piper) |
| `aufnahmen/` | entsteht beim Aufnehmen: Roh-WAVs 48 kHz/24 Bit mono, `<id>.wav` |
| `export-22050/` | entsteht beim Export: `wavs/`, `metadata.csv` (`id|text`, Piper/LJSpeech), `liste.txt` (`wavs/id.wav|text`) |

**Satzquelle:** Common Voice Deutsch, `sentence-collector.txt` + `wiki.de.rerun-2022-08.txt` (CC0) und eigene Sätze (CC0).
- **Filter:** 5–14 Wörter, keine Ziffern und Abkürzungen, nur Wörter, die im Korpus mindestens 3× vorkommen (keine exotischen Eigennamen), keine heiklen Themen.
- **Auswahl:** gierig nach Phonem- und Diphon-Abdeckung. 1018/1018 Diphone des Pools sind abgedeckt, ~10 % sind Fragen.

## Aufnehmen

```bash
cd voice && python3 aufnahme.py
```

**Bedienung:**
- **Leertaste:** Aufnahme starten. Nochmal Leertaste stoppt und speichert sofort.
- **Enter / →** weiter, **←** zurück, **P** anhören, **S** überspringen.
- Nach jedem Satz erscheint eine Ampel: Pegel, Übersteuerung, Rauschen, Länge.
  - Rot heißt: neu aufnehmen (Leertaste überschreibt).
  - Die Aufnahme lässt sich jederzeit beenden. Beim nächsten Start geht es beim ersten offenen Satz weiter.
- **Vor dem Start einmal „Raumrauschen messen“ drücken.** Ziel: unter −55 dBFS.

### Mikrofon, Raum, Sprechweise

- **Mikrofon:**
  - Am besten USB- oder XLR-Mikro bzw. Headset-Mikro; das Kameramikro der Webcam reicht nicht.
  - Immer **dasselbe Mikro, gleiche Position**, alle Sitzungen.
- **Abstand:** 15–25 cm, leicht seitlich am Mund vorbei (gegen Plopp-Laute). Mit Popschutz, wenn vorhanden.
- **Pegel:** Sprachspitzen bei −12 bis −6 dBFS (gelber Bereich nur kurz streifen, nie rot).
  - Pegel in den System-Toneinstellungen (pavucontrol) einstellen, nicht während der Aufnahmen ändern.
  - **Rauschunterdrückung, AGC und Effekte aus.**
- **Raum:**
  - Klein und möbliert ist besser als groß und leer. Vorhänge zu, Teppich, Kleiderschrank offen hilft.
  - Lüfter und Heizungsrauschen möglichst weg; Handy stumm.
  - Den PC-Lüfter nicht neben das Mikro.
- **Sprechen:**
  - Natürlich und ruhig, so wie NuOrb klingen soll; nicht vorlesen-monoton, nicht schauspielern.
  - Gleiche Stimmung und Lautstärke über alle Sitzungen.
  - Satz erst lesen, dann Leertaste, 0,5 s still, sprechen, 0,5 s still, Leertaste.
  - Versprecher → einfach neu aufnehmen.
  - Satzzeichen ernst nehmen: Fragen als Fragen, Ausrufe mit etwas Energie.
- **Sitzungen:**
  - 20–30 min am Stück, dann Pause und Wasser trinken.
  - Nicht verschnupft oder heiser aufnehmen.
  - Lieber 3 Tage à 20 min als 1 Tag à 60 min.

### Wie viel?

| Verfahren | Benötigt | Sätze |
|---|---|---|
| Piper-Fine-Tune (thorsten als Basis) | brauchbar ab ~20 min, gut ab 45–60 min | 300 / 650–850 |
| **Kokoro-Fine-Tune** (HUI-Basis) | Vorbilder: 455–627 Clips (~0,5–1 h) | **600–1000** |
| IMS-Toucan | laut Paper ab ~30 min | 400+ |

**Ziel also: mindestens 600, besser alle 1000 Sätze.**

## Freies Erzählen (statt oder zusätzlich zum Vorlesen)

**Aufnehmen:** `bash frei-aufnehmen.sh`. Das Mikro ist das AT2020USB+, eine Datei pro Sitzung nach `frei/`, Ende mit `q`.

**Verarbeiten:**

```bash
python3 frei-verarbeiten.py pruefe        # Feedback zur neuesten Aufnahme: Pegel, Rauschen, Brummen, Pausen
```

```bash
python3 frei-verarbeiten.py alles         # an Pausen in 3–12-s-Clips schneiden + auf nuorb transkribieren
```

```bash
python3 aufnahme.py export --rate 22050   # gelesene Sätze + freie Clips zusammen -> export-22050/
```

Was dabei passiert:
- **Schneiden:**
  - An Pausen von mindestens 0,25 s. Eine Pause ab 0,6 s beendet einen Clip, sobald er 3 s lang ist.
  - 0,2 s Rand bleibt dran, nichts wird über 12 s lang.
  - Hat ein Stück über 12 s gar keine Pause, wird es an der leisesten Stelle geteilt. Der Clip bekommt `_h` im Namen und landet nicht im Export.
- **Transkription:**
  - Mit Parakeet (sherpa-onnx), dem Modell, das auf nuorb schon läuft. Nur CPU, ~0,1–0,3 × Echtzeit.
  - Das Audio geht nur ins LAN und wird auf nuorb danach sofort gelöscht.
  - Clips mit Auffälligkeiten (harter Schnitt, kein Text, unplausibles Tempo, Ende evtl. abgeschnitten) kommen nach `frei-clips/transkript-ausgeschlossen.tsv`.
- **Wichtig – einmal durchlesen:** Der Text in `frei-clips/transkript.tsv` muss **exakt** dem Gesagten entsprechen.
  - Parakeet lässt „äh“ und Wiederholungen meist weg und schreibt Zahlen als Ziffern („14.30 Uhr“, „Dr.“).
  - Solche Zeilen korrigieren (Zahlen ausschreiben) oder löschen. Ein Clip mit „äh“ im Ton und ohne „äh“ im Text lehrt das Modell Unsinn.
- **Getestet** mit synthetischer Probe: 58 s Audio ergaben 8 Clips, alle Sätze korrekt erkannt.

## Ehrlichkeitsrechnung: Wie viel Aufnahme braucht es wirklich?

**Nutzbare** Minuten sind die nach dem Schneiden, Aussortieren und Korrigieren.

- **Freies Erzählen:** Erfahrungsgemäß bleiben **60–75 %** übrig. Abzüge sind Pausen, Füllwörter, abgebrochene Sätze und Lachen. 10 min Erzählen ergeben also ~6–7 min Trainingsmaterial.
- **Vorlesen:** Es bleiben ~90 % übrig.

| Ziel | Piper-Fine-Tune (thorsten-Basis) | Kokoro-Fine-Tune (HUI-Basis) |
|---|---|---|
| erkennbar „du“, aber mit Artefakten | ~15–20 min nutzbar | ~20–30 min (unbestätigt) |
| **gut für den Alltag** | **~45–60 min** nutzbar | **~45–60 min** (Vorbilder: 455–627 Clips) |
| sehr gut | 2 h + | 2 h + |

Alle Werte sind Erfahrungswerte aus der Community, keine Herstellerangaben.

**Umgerechnet auf freies Erzählen:**
- „gut“ braucht etwa **70–90 min Rohaufnahme**.
- Sitzungen von 1 min reichen also nicht weit; 5–15 min am Stück sind praktischer.
- **Empfehlung:** freies Erzählen (natürliche Sprechmelodie, ideal für einen Gesprächs-Assistenten) **plus 300–500 gelesene Sätze** aus `saetze.tsv`.
  - Die decken die Laute und Zahlen/Uhrzeiten systematisch ab, die beim freien Reden zufällig fehlen.
  - 500 Sätze sind ~36 min, davon ~32 min nutzbar.

**Zero-Shot-Klon als Brücke:** Klont aus 5–15 s Referenz sofort, ohne Training.

| | F5-TTS German (HPI) | Qwen3-TTS |
|---|---|---|
| Lizenz | Code MIT, **Gewichte CC-BY-NC-4.0** (privat ok, nicht kommerziell) | Apache-2.0 |
| braucht | 5–15 s saubere Referenz | 3–10 s Referenz |
| läuft auf | **nur GPU** | **nur GPU** |
| Downloads | PyTorch-ROCm (~4–6 GB) + Modell ~1,3 GB (unbestätigt) | PyTorch-ROCm + Modell ~1,5–4 GB (unbestätigt) |
| VRAM | ~2–4 GB (unbestätigt): neben Gemma (3,1 GiB frei) zu knapp, Ruckelgefahr → **nur im Modus Remote** | ähnlich |

**Lohnt sich die Brücke? Ehrlich gesagt nur begrenzt.**
- **Ja, als Hörprobe:** Schon nach der ersten Aufnahme hört man, wie „NuOrb mit deiner Stimme“ klingen könnte. Kostet einen Abend Einrichtung plus ~6 GB Download.
- **Nicht als Alltagsstimme:** Sie braucht die GPU (Gemma muss weichen) und kann nicht auf nuorb laufen.
- **Als Datenquelle** (synthetische Sätze für das Piper/Kokoro-Training):
  - Nur mit **Qwen3-TTS** (Apache). Bei F5 wären die Trainingsdaten aus einem Nicht-kommerziell-Modell abgeleitet. Privat unkritisch, aber unsauber.
  - Hilft nur, wenn echte Aufnahmen knapp bleiben (< 20 min nutzbar). Fehler des Klons werden mitgelernt.
- **Empfehlung:** Ohne Brücke direkt Richtung Piper, sobald ~30 min nutzbar sind. Die Brücke nur, wenn der Nutzer vorher eine Hörprobe will.

## Export für das Training

```bash
python3 aufnahme.py export --rate 22050   # Piper (22,05 kHz)
```

```bash
python3 aufnahme.py export --rate 24000   # Kokoro (24 kHz)
```

Der Export macht pro Datei:
- Stille vorn und hinten abschneiden (0,15 s Rand bleibt).
- Sprach-Lautheit auf −20 dBFS angleichen, Spitze ≤ −1 dBFS.
- Hochpass 60 Hz (entfernt Trittschall/Rumpeln unterhalb der Stimme).
- Mono, 16 Bit.

Die Rohdaten bleiben unverändert.

## Ziel (präzisiert vom Nutzer)

Training auf der PC-GPU, danach spricht das Modell **Text in der Stimme des Nutzers**, möglichst **auf der CPU von nuorb in Echtzeit**.
- Eine GPU-Ausgabe kommt nur infrage, wenn sie hörbar deutlich besser ist.
- VRAM spielt nur während des Trainings eine Rolle.
- Das frühere Projekt ist nicht erreichbar. Laut Erinnerung war es „StyleTTS2 oder etwas Deutsches“ und brauchte eine GPU fürs Training.

## Modellvergleich (Primärquellen geprüft 2026-11-24, ohne Hörtest)

| Kandidat | Lizenz Code / Gewichte | Training (Daten / VRAM / ROCm) | Ausgabe auf nuorb-CPU | Deutsch |
|---|---|---|---|---|
| **Piper-Fine-Tune** (piper1-gpl, Basis thorsten medium) | GPL-3.0 / thorsten CC0 (Checkpoints MIT-getaggt) | `wav\|Text`, 22050 Hz. Bei < 5 h laut Doku ~2000 Epochen. Ab ~8 GB VRAM (Batch 16–64). AMD: „Erfolg mit RX 7600“ gemeldet. | **Ja**, ONNX eingebaut. Gemessen thorsten medium: RTF 0,08, ~45 ms bis Audio. Läuft heute schon in Hermes. | gut verständlich, Prosodie eher flach |
| **Kokoro-82M-Fine-Tune** (StyleTTS2-Familie, Rezept kikiri-tts, Basis „kokoro-deutsch-hui-base“) | Apache-2.0 / Apache-2.0, HUI-Basis CC0 | Zwei StyleTTS2-Stufen (Akustik, dann GAN + WavLM). Beispielstimmen mit nur **455–627 Clips** (~0,5–1 h). VRAM „10 GB+“, Batch 4 auf 12 GB. ROCm laut kikiri **nur fp32**, fp16 hängt; erste MIOpen-Kompilierung 10–30 min. | **wahrscheinlich ja**: „Echtzeit oder schneller“ laut Modellkarte, Fremd-Benchmark ONNX RTF ~0,64. Auf nuorb noch zu messen. ONNX-Export des deutschen Fine-Tunes unbestätigt. | **natürlicher als Piper** (Thorsten-Kokoro) |
| **StyleTTS2** pur (Columbia) | MIT / Pretrained mit Auflage: Hörer informieren, dass die Stimme synthetisch ist (außer mit Zustimmung des Sprechers) | Fine-Tune ~1 h Daten, Beispiel 4 h auf 4× A100. Deutsch nur über multilingualen PL-BERT oder Umbau. | ja, aber Diffusion in PyTorch, langsamer als Kokoro | kein fertiges deutsches Modell. **Kokoro ist der praktische deutsche StyleTTS2-Weg** |
| **IMS-Toucan** (Uni Stuttgart) | Apache-2.0 / Apache-2.0 | `--finetune` vorhanden. Paper: 30 min reichen für neuen Sprecher und neue Sprache. VRAM, ROCm und Zeit nicht dokumentiert. Seit v3.0 (2024) kein neues Release. | laut README „keine GPU nötig“, RTF unbestätigt | ja (Mehrsprachen-Modell), Qualität gegenüber Kokoro unbekannt |
| F5-TTS German (HPI) | MIT / **CC-BY-NC-4.0** | Zero-Shot ab 5–15 s | **nein**, GPU | gut |
| IndexTTS 2.5 German | bilibili-Lizenz (Schwellen, kommerziell nur auf Anfrage) | LoRA, 0,8 B Parameter | **nein**, GPU | gut (WER 5,35 %) |
| MiraToffel (miraTTS DE) | / **CC-BY-NC-SA-4.0**, gated | 0,5 B Parameter | **nein**, GPU | ja, 48 kHz |
| Kartoffelbox (Chatterbox DE) | MIT / MIT | 0,5 B Parameter | CPU-Fallback, aber nicht echtzeitfähig (vermutet) | ja |
| Qwen3-TTS | Apache-2.0 / Apache-2.0 | Klon aus 3–10 s | **nein**, GPU, Streaming ~100 ms | offiziell |

- **Fallen raus,** weil sie nur mit GPU sprechen: F5, IndexTTS, MiraToffel, Kartoffelbox, Qwen3-TTS.
- **Bleibt Reserve:** Qwen3-TTS, nur für den Fall, dass die CPU-Stimmen hörbar deutlich schlechter klingen.
- **XTTS-v2 und GPT-SoVITS:** nicht kommerziell nutzbar bzw. kein Deutsch.

**ROCm:** Die RX 7800 XT (gfx1101) ist laut AMD in ROCm 7.x offiziell unterstützt (für Ubuntu/RHEL). Auf CachyOS wahrscheinlich ohne `HSA_OVERRIDE_GFX_VERSION`, aber unbestätigt.

## Entscheidung

Beide Wege bauen auf denselben Aufnahmen auf und enden mit einer Stimme, die auf nuorb ohne GPU spricht.

1. **Hauptweg: Kokoro-Fine-Tune** (StyleTTS2-Familie, passt zur Erinnerung „StyleTTS2“)
   - Klingt natürlicher als Piper.
   - Komplett Apache/CC0.
   - Datenmenge passt: Die Vorbilder kamen mit 455–627 Clips aus, das sind ~0,5–1 h. **Also 600–1000 Sätze aufnehmen.**
2. **Sicherheitsnetz: Piper-Fine-Tune** (thorsten medium als Basis)
   - Dieselben Aufnahmen, Export auf 22050 Hz.
   - Am besten dokumentiert, Hermes kann es sofort (`tts.piper.voice`).
   - Schnellste Ausgabe (~45 ms).
   - Wird zuerst trainiert, weil es kürzer und risikoärmer ist. Dann gibt es schnell ein erstes Ergebnis zum Anhören.
3. **IMS-Toucan** nur, falls beide nicht überzeugen.

Danach entscheidet ein **Hörtest**: Piper-eigen gegen Kokoro-eigen gegen thorsten. Gemessen wird auf nuorb die Zeit bis zum ersten Audio und die RTF.

- Wenn Kokoro auf nuorb schnell genug ist (RTF < 0,5), wird es die Standardstimme.
- Sonst Kokoro für längere Antworten und Piper für kurze. Oder einfach Piper.

**Einwilligung:** Es ist die eigene Stimme des Nutzers. StyleTTS2-Auflage (Hinweis auf synthetische Stimme) gilt damit als erfüllt, solange die Stimme nur für NuOrb genutzt wird.

## VRAM und Trainingsbetrieb

Gemma belegt mit dem Desktop bis 12,9 GiB, frei bleiben ~3,1 GiB.

| Bedarf | VRAM | passt neben Gemma? |
|---|---|---|
| Piper-Training (Batch 16–32) | ~8–10 GB | **nein** |
| Kokoro-Training (fp32, Batch 2–4) | ~10–12 GB | **nein** |
| Ausgabe Piper / Kokoro | 0 (läuft auf nuorb-CPU) | egal |

**Training also nur im Wechselbetrieb, Ablauf:**
1. **Der Nutzer stimmt dem Training zu.**
2. **Gehirn-Modus auf „Remote“.**
   - Das macht der Nutzer selbst (Admin-Panel oder Handy) oder es geschieht mit seiner Zustimmung über nuorb-admin `/internal/brain`.
   - Gemma wird dabei sofort aus dem PC-VRAM entladen. NuOrb antwortet in der Zeit über Claude.
3. **Mit `rocm-smi --showmeminfo vram` prüfen,** dass das VRAM frei ist (nur noch der Desktop belegt ~1–2 GiB). Sonst nicht starten.
4. **Training mit VRAM-Deckel 0,75** (Details siehe unten).
5. **Danach den Modus zurück auf die vorherige Wahl des Nutzers stellen.** Diese Wahl wird in Schritt 2 notiert.

- **VRAM-Deckel für das Training:**
  - Im Trainingsskript `torch.cuda.set_per_process_memory_fraction(0.75)` (≈ 12 GiB).
  - So bleiben ≥ 3–4 GiB für Desktop und Compositor.
  - Batch-Größe so wählen, dass das reicht (Piper 16, Kokoro 2–4).
- **Zeitfenster:** abends, nachts oder während der Nutzer weg ist. Volle GPU-Rechenlast lässt den Desktop auch bei freiem VRAM etwas zäher reagieren.
- **Checkpoints alle ~30 min:**
  - Das Training lässt sich jederzeit stoppen (Gemma wieder laden) und später fortsetzen.
  - Ein kleines Start/Stopp-Skript prüft Schritt 3 automatisch und erinnert am Ende an Schritt 5.
- **Dauer (grob, unbestätigt):**
  - Piper: Stunden bis ~1 Tag (2000 Epochen bei < 1 h Audio, kleines Modell).
  - Kokoro: Stage 1 + Stage 2 eher ein bis mehrere Nächte. kikiri meldet auf ROCm ~4,8 h pro Epoche bei 11,5k Clips; bei ~800 Clips grob 20 min pro Epoche.

## Nächste Schritte nach Rückkehr (je mit Zustimmung und Größenangabe)

1. **Aufnehmen.** Zuerst 10 Sätze zum Pegel-Check, dann Sitzungen à 20–30 min bis 600–1000 Sätze.
2. **PyTorch-ROCm-Umgebung auf dem PC** (~4–6 GB Download). Kurztest auf der GPU, ob fp32-Training stabil läuft.
3. **Piper-Fine-Tune.**
   - Download: thorsten-medium-Checkpoint (~800 MB, unbestätigt).
   - Erst ein kurzer Probelauf, dann über Nacht.
4. **Kokoro-Fine-Tune** über kikiri-tts.
   - Download: Repo, Kokoro-82M, HUI-Basis, WavLM, zusammen grob 2–3 GB (unbestätigt, wird vorher genau geprüft).
5. **Auf nuorb messen und Hörtest,** dann in Hermes eintragen.
   - Piper: `tts.piper.voice`.
   - Kokoro: über einen kleinen lokalen TTS-Dienst wie beim STT-Router (Hermes-Anbindung prüfen).

### Quellen (Auswahl)

- Piper Training: https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/TRAINING.md
- Piper Checkpoints: https://huggingface.co/datasets/rhasspy/piper-checkpoints
- Qwen3-TTS: https://github.com/QwenLM/Qwen3-TTS und https://arxiv.org/abs/2601.15621
- F5-TTS-German: https://huggingface.co/aihpi/F5-TTS-German
- Kokoro Thorsten: https://huggingface.co/Thorsten-Voice/Kokoro und https://github.com/semidark/kikiri-tts (docs/TRAINING_GUIDE.md, docs/TROUBLESHOOTING.md)
- kokoro-onnx: https://github.com/thewh1teagle/kokoro-onnx
- StyleTTS2: https://github.com/yl4579/StyleTTS2
- IMS-Toucan: https://github.com/DigitalPhonetics/IMS-Toucan und https://huggingface.co/Flux9665/ToucanTTS
- IndexTTS 2.5 German: https://huggingface.co/sharrnah/index-tts-2.5-german
- MiraToffel: https://huggingface.co/SebastianBodza/MiraToffel_miraTTS_german und Kartoffelbox: https://huggingface.co/SebastianBodza/Kartoffelbox-v0.1
- ROCm Systemanforderungen: https://rocm.docs.amd.com/projects/install-on-linux/en/latest/reference/system-requirements.html
- Chatterbox Multilingual: https://resemble.ai/introducing-chatterbox-multilingual-open-source-tts-for-23-languages
- GPT-SoVITS (Sprachen): https://github.com/RVC-Boss/GPT-SoVITS
- Common Voice Sätze: https://github.com/common-voice/common-voice/tree/main/server/data/de
