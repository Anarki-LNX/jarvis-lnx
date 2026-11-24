"""Demo-Modus der NuOrb-UI: simulierte Hermes-Runs im selben Ereignisformat wie /v1/runs/{id}/events.

Kein LLM-Aufruf. STT und Piper bleiben echt. Gedacht fuer die Zeit, in der Hermes-Runs pausiert sind
(jeder Run laedt sonst ein 14-GB-Modell auf die Desktop-GPU des Nutzers).
Ereignisse: run.started? -> reasoning.available, tool.started/completed, approval.request (bei Loesch-
Wuenschen), message.delta (wortweise), run.completed / run.cancelled.
"""
from __future__ import annotations

import asyncio
import json
import re
import secrets
import shutil
import time
from datetime import datetime

RUNS: dict[str, dict] = {}
WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
          "November", "Dezember"]


def _ev(run_id: str, name: str, **fields) -> bytes:
    payload = {"event": name, "run_id": run_id, "timestamp": time.time(), **fields}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()


def create(text: str, session_id: str) -> dict:
    run_id = "demo_" + secrets.token_hex(8)
    RUNS[run_id] = {"text": text, "session_id": session_id, "approval": None, "decision": asyncio.Event(),
                    "choice": None, "stop": False, "output": None, "created": time.time()}
    for rid in [r for r, v in RUNS.items() if time.time() - v["created"] > 900]:
        RUNS.pop(rid, None)
    return {"run_id": run_id, "session_id": session_id, "status": "started", "mode": "demo"}


def _plan(text: str) -> dict:
    t = text.lower()
    now = datetime.now()
    if re.search(r"l[öo]sch|entfern|rm -rf|weg ?mach|formatier", t):
        return {"tool": ("terminal", "rm -rf ~/demo/alter-ordner"), "approval": True}
    if re.search(r"uhr|spät|zeit", t):
        return {"answer": f"Es ist {now.hour} Uhr {now.minute:02d}. Zeit für etwas Großes – oder wenigstens für Kaffee."}
    if re.search(r"datum|welcher tag|heute", t):
        return {"answer": f"Heute ist {WOCHENTAGE[now.weekday()]}, der {now.day}. {MONATE[now.month - 1]}."}
    if re.search(r"festplatte|speicher|platz", t):
        du = shutil.disk_usage("/")
        used, total = du.used / 1e9, du.total / 1e9
        return {"tool": ("terminal", "df -h /"),
                "answer": f"Auf nuorb sind {used:.0f} von {total:.0f} Gigabyte belegt, also etwa "
                          f"{100 * used / total:.0f} Prozent. Reichlich Platz."}
    if re.search(r"wetter", t):
        return {"answer": "Für das Wetter habe ich noch keine Quelle. Ich schaue im Moment eher nach innen."}
    if re.search(r"wer bist du|stell dich vor|hallo|hi nuorb|guten (morgen|tag|abend)", t):
        return {"answer": "Ich bin NuOrb, dein persönlicher Assistent. Gerade läuft der Demo-Modus: "
                          "Ich höre und spreche echt, nur mein Gehirn macht Pause."}
    return {"answer": f"Demo-Modus: Ich habe verstanden: „{text.strip()[:160]}“. "
                      "Antworten kann ich erst, wenn mein Gehirn wieder freigegeben ist."}


async def events(run_id: str):
    run = RUNS.get(run_id)
    if not run:
        yield _ev(run_id, "run.failed", error="Unbekannter Demo-Lauf")
        return
    plan = _plan(run["text"])
    yield b": demo\n\n"
    await asyncio.sleep(0.5)
    yield _ev(run_id, "reasoning.available", text="")
    await asyncio.sleep(0.7)
    answer = plan.get("answer", "")
    if plan.get("tool"):
        tool, preview = plan["tool"]
        call_id = "call_" + secrets.token_hex(4)
        yield _ev(run_id, "tool.started", tool=tool, preview=preview, tool_call_id=call_id)
        if plan.get("approval"):
            req = "demo-" + secrets.token_hex(6)
            run["approval"] = req
            yield _ev(run_id, "approval.request", request_id=req, execution_generation=1,
                      command=preview, description="Demo: Hermes will einen Ordner rekursiv löschen. "
                                                    "Es wird nichts wirklich ausgeführt.",
                      choices=["once", "deny"])
            try:
                await asyncio.wait_for(run["decision"].wait(), timeout=120)
            except asyncio.TimeoutError:
                run["choice"] = "deny"
            yield _ev(run_id, "approval.responded", choice=run["choice"], request_id=req, resolved=1)
            if run["stop"]:
                yield _ev(run_id, "run.cancelled")
                return
            ok = run["choice"] == "once"
            await asyncio.sleep(0.6)
            yield _ev(run_id, "tool.completed", tool=tool, tool_call_id=call_id, duration=0.6, error=not ok,
                      preview="(simuliert)" if ok else "BLOCKED: abgelehnt")
            answer = ("Erledigt. Der Ordner ist weg – natürlich nur im Demo-Modus, es wurde nichts gelöscht."
                      if ok else "Verstanden, ich lasse den Ordner in Ruhe.")
        else:
            await asyncio.sleep(0.8)
            yield _ev(run_id, "tool.completed", tool=tool, tool_call_id=call_id, duration=0.8, error=False,
                      preview="(Demo)")
    for word in re.findall(r"\S+\s*", answer):
        if run["stop"]:
            yield _ev(run_id, "run.cancelled")
            return
        yield _ev(run_id, "message.delta", delta=word)
        await asyncio.sleep(0.045)
    run["output"] = answer
    yield _ev(run_id, "run.completed", output=answer, usage={}, runtime={"provider": "demo", "model": "demo"})


def approve(run_id: str, choice: str) -> dict:
    run = RUNS.get(run_id)
    if not run or not run["approval"]:
        return {"error": {"message": "keine offene Bestätigung"}, "_status": 409}
    run["choice"] = choice
    run["decision"].set()
    return {"object": "hermes.run.approval_response", "run_id": run_id, "choice": choice,
            "request_id": run["approval"], "resolved": 1}


def stop(run_id: str) -> None:
    run = RUNS.get(run_id)
    if run:
        run["stop"] = True
        run["choice"] = run["choice"] or "deny"
        run["decision"].set()


def status(run_id: str) -> dict:
    run = RUNS.get(run_id) or {}
    return {"object": "hermes.run", "run_id": run_id, "status": "completed" if run.get("output") else "running",
            "output": run.get("output")}
