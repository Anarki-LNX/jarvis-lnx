#!/usr/bin/env python3
"""Mini-Mock für Tests: tut so, als wäre es Ollama (/api/version, /api/tags) und ein OpenAI-kompatibles LLM
(/v1/models, /v1/chat/completions mit und ohne Stream). Antwortet immer mit einem festen Satz plus Echo.
Keine GPU, kein Netz. Start: python3 docker/tools/mock-llm.py [port]   (Standard 18434, nur 127.0.0.1)
Werkzeug-Test: Enthält die Nutzerfrage [[tool:<endung> <json>]], ruft der Mock das angebotene Werkzeug auf, dessen Name
auf <endung> endet (z. B. [[tool:smarthome_schalten__schalten {"name":"Küchenlicht","aktion":"aus"}]]); nach dem
Werkzeug-Ergebnis antwortet er mit „Erledigt: <Ergebnis>“.
"""
import re
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 18434
MODEL = "mock-nuorb"


def answer(msgs):
    last = next((m for m in reversed(msgs) if m.get("role") == "user"), {})
    c = last.get("content")
    if isinstance(c, list):
        c = " ".join(x.get("text", "") for x in c if isinstance(x, dict))
    return f"Testantwort vom Mock-Gehirn. Du hast gefragt: {str(c)[-80:]}"


def tool_call(body):
    """Werkzeugaufruf, wenn die letzte Nutzerfrage den Test-Marker trägt und noch kein Ergebnis da ist."""
    msgs = body.get("messages") or []
    if msgs and msgs[-1].get("role") == "tool":
        return None
    last = next((m for m in reversed(msgs) if m.get("role") == "user"), {})
    c = last.get("content")
    if isinstance(c, list):
        c = " ".join(x.get("text", "") for x in c if isinstance(x, dict))
    m = re.search(r"\[\[tool:(\S+) (\{.*?\})\]\]", str(c or ""))
    if not m:
        return None
    names = [t.get("function", {}).get("name", "") for t in body.get("tools") or []]
    name = next((n for n in names if n.endswith(m.group(1))), None)
    if not name:
        return {"missing": m.group(1), "names": names}
    return {"name": name, "arguments": m.group(2)}


def after_tool(msgs):
    if msgs and msgs[-1].get("role") == "tool":
        c = msgs[-1].get("content")
        if isinstance(c, list):
            c = " ".join(x.get("text", "") for x in c if isinstance(x, dict))
        return f"Erledigt: {str(c)[:1500]}"
    return None


class H(BaseHTTPRequestHandler):
    def log_message(self, f, *a):
        print("mock", f % a, flush=True)

    def js(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        p = self.path.split("?")[0].rstrip("/")
        if p == "/api/version":
            return self.js(200, {"version": "0.0.0-mock"})
        if p == "/api/tags":
            return self.js(200, {"models": [{"name": MODEL, "size": 1}]})
        if p == "/api/ps":
            return self.js(200, {"models": []})
        if p in ("/v1/models", "/models"):
            return self.js(200, {"object": "list", "data": [{"id": MODEL, "object": "model", "owned_by": "mock"}]})
        self.js(404, {"error": "not found"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        p = self.path.split("?")[0].rstrip("/")
        if p == "/api/generate":
            return self.js(200, {"done": True})
        if p == "/api/show":  # Hermes fragt die echte Kontextgröße ab
            return self.js(200, {"parameters": "num_ctx                        65536",
                                 "model_info": {"general.architecture": "mock", "mock.context_length": 65536},
                                 "capabilities": ["completion", "tools"]})
        if not p.endswith("/chat/completions"):
            return self.js(404, {"error": "not found"})
        msgs = body.get("messages") or []
        tc = tool_call(body)
        if tc and "missing" in tc:
            print("mock: Werkzeug fehlt", tc["missing"], "angeboten:", tc["names"][:40], flush=True)
            tc = None
        text = after_tool(msgs) or answer(msgs)
        cid, now = f"chatcmpl-mock{int(time.time()*1000)}", int(time.time())
        usage = {"prompt_tokens": 10, "completion_tokens": 12, "total_tokens": 22}
        if tc:
            call = {"id": f"call_{int(time.time()*1000)}", "type": "function", "function": tc}
            if not body.get("stream"):
                return self.js(200, {"id": cid, "object": "chat.completion", "created": now, "model": MODEL,
                                     "choices": [{"index": 0, "message": {"role": "assistant", "content": None, "tool_calls": [call]},
                                                  "finish_reason": "tool_calls"}], "usage": usage})
            self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
            base = {"id": cid, "object": "chat.completion.chunk", "created": now, "model": MODEL}
            for d in ({"role": "assistant", "content": None, "tool_calls": [{"index": 0, **call}]},):
                self.wfile.write(b"data: " + json.dumps({**base, "choices": [{"index": 0, "delta": d, "finish_reason": None}]}).encode() + b"\n\n")
            self.wfile.write(b"data: " + json.dumps({**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}], "usage": usage}).encode() + b"\n\n")
            self.wfile.write(b"data: [DONE]\n\n"); self.wfile.flush()
            return
        if not body.get("stream"):
            return self.js(200, {"id": cid, "object": "chat.completion", "created": now, "model": MODEL,
                                 "choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                                              "finish_reason": "stop"}], "usage": usage})
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        def ev(d):
            self.wfile.write(b"data: " + json.dumps(d).encode() + b"\n\n"); self.wfile.flush()
        base = {"id": cid, "object": "chat.completion.chunk", "created": now, "model": MODEL}
        ev({**base, "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}]})
        for w in text.split(" "):
            ev({**base, "choices": [{"index": 0, "delta": {"content": w + " "}, "finish_reason": None}]})
        ev({**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}], "usage": usage})
        self.wfile.write(b"data: [DONE]\n\n"); self.wfile.flush()


ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
