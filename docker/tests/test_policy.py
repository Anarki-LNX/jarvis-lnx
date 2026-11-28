"""Unit-Tests für die Sicherheitsregeln der Werkzeuge (S5/S6): docker/app/nuorb_policy.py und die Hilfen in nuorb_common."""
from __future__ import annotations

import json
import unittest

from _lade import APP, lade, temp_ordner

T = temp_ordner("policy")
pol = lade("nuorb_policy_test", APP / "nuorb_policy.py", {"HERMES_HOME": str(T)})
jc = lade("nuorb_common_policy_test", APP / "nuorb_common.py", {"HERMES_HOME": str(T), "NUORB_MODELS": str(T / "models")})


def pre(tool: str, args: dict | None = None, session: str = "s1"):
    return pol.decide("pre", {"tool_name": tool, "tool_input": args or {}, "session_id": session})


def post(tool: str, session: str = "s1"):
    return pol.decide("post", {"tool_name": tool, "tool_input": {}, "session_id": session})


class FremdeInhalte(unittest.TestCase):
    def setUp(self):
        for f in pol.MARKS.glob("*.json") if pol.MARKS.exists() else []:
            f.unlink()

    def test_ohne_fremde_inhalte_keine_rueckfrage(self):
        self.assertIsNone(pre("mcp__smarthome_schalten__schalten", {"name": "Licht"}))
        self.assertIsNone(pre("cronjob_manage", {"action": "create"}))

    def test_nach_webseite_braucht_aktion_bestaetigung(self):
        self.assertIsNone(post("web_extract"))
        out = pre("mcp__nuorb__name_setzen", {"name": "Hacker"})
        self.assertEqual(out["action"], "approve")
        self.assertIn("web_extract", out["message"])
        self.assertEqual(pre("cronjob_manage")["action"], "approve")
        self.assertEqual(pre("mcp__fremd__irgendwas")["action"], "approve")   # vom Nutzer hinzugefügter MCP-Server

    def test_markierung_gilt_nur_fuer_die_sitzung(self):
        post("web_search", session="a")
        self.assertIsNone(pre("cronjob_manage", session="b"))
        self.assertEqual(pre("cronjob_manage", session="a")["action"], "approve")

    def test_markierung_bleibt_ueber_den_durchgang_hinaus(self):
        post("browser_exec")
        for _ in range(3):   # jede weitere Frage derselben Sitzung
            self.assertEqual(pre("memory", {"action": "add"})["action"], "approve")

    def test_eigene_lesende_werkzeuge_markieren_nicht_und_brauchen_nichts(self):
        post("mcp__smarthome__geraete")
        post("mcp__wetter__wetter")
        self.assertIsNone(pre("cronjob_manage"))
        post("web_extract")
        self.assertIsNone(pre("mcp__smarthome__zustand"))   # lesen bleibt frei
        self.assertIsNone(pre("mcp__wetter__wetter"))

    def test_jede_rueckfrage_hat_eigenen_schluessel(self):
        post("web_extract")
        self.assertNotEqual(pre("cronjob_manage")["rule_key"], pre("cronjob_manage")["rule_key"])   # kein „immer erlauben“

    def test_alte_markierung_laeuft_ab(self):
        post("web_extract")
        f = pol.mark_file("s1")
        f.write_text(json.dumps({"t": 0, "tool": "web_extract"}))
        self.assertIsNone(pre("cronjob_manage"))


class Heimnetz(unittest.TestCase):
    def setUp(self):
        (T / "config.yaml").write_text("model:\n  base_url: http://192.168.1.50:11434/v1\n")

    def test_private_ziele_gesperrt(self):
        for cmd in ("curl http://192.168.178.50/", "wget 172.16.0.5", "curl http://localhost:8642/v1/runs",
                    "curl http://127.0.0.1:8444/api/auth/state", "curl http://homeassistant.local:8123", "curl http://[::1]:8443/"):
            out = pre("terminal", {"command": cmd})
            self.assertEqual((out or {}).get("action"), "block", cmd)

    def test_eingetragene_adresse_erlaubt(self):
        self.assertIsNone(pre("terminal", {"command": "curl http://192.168.1.50:11434/api/tags"}))

    def test_eingetragene_loopback_adresse_gibt_nicht_den_container_frei(self):
        (T / "config.yaml").write_text("model:\n  base_url: http://127.0.0.1:18434/v1\nstt: http://127.0.0.1:8178/v1\n")
        self.assertIsNone(pre("terminal", {"command": "curl http://127.0.0.1:18434/api/tags"}))
        for cmd in ("curl -sk https://127.0.0.1:8444/api/auth/state", "curl http://127.0.0.1:8642/v1/runs", "curl 127.0.0.1"):
            self.assertEqual((pre("terminal", {"command": cmd}) or {}).get("action"), "block", cmd)

    def test_anderer_port_derselben_adresse_gesperrt(self):
        self.assertEqual(pre("terminal", {"command": "curl http://192.168.1.50:22/"})["action"], "block")
        self.assertIsNone(pre("terminal", {"command": "ping 192.168.1.50"}))   # ohne Port: Host steht in der Konfiguration

    def test_oeffentliche_adresse_und_andere_werkzeuge_frei(self):
        self.assertIsNone(pre("terminal", {"command": "curl https://93.184.215.14/"}))
        self.assertIsNone(pre("web_search", {"query": "192.168.178.50 router"}))   # Hermes prüft web_* selbst

    def test_python_und_browser_auch(self):
        self.assertEqual(pre("execute_code", {"code": "import urllib.request; urllib.request.urlopen('http://192.168.178.50')"})["action"], "block")
        self.assertEqual(pre("browser_exec", {"code": "goto('http://172.16.0.6/admin')"})["action"], "block")


class Konfiguration(unittest.TestCase):
    def test_enger_standard_und_hooks(self):
        data: dict = {"hooks": {"pre_tool_call": [{"command": "/eigener/hook.sh"}]}}
        self.assertTrue(jc.apply_tools_policy(data, "narrow"))
        self.assertEqual(data["platform_toolsets"]["api_server"], jc.TOOLSETS["narrow"])
        self.assertNotIn("terminal", data["platform_toolsets"]["api_server"])
        pre_h = data["hooks"]["pre_tool_call"]
        self.assertTrue(pre_h[0]["command"].endswith("nuorb_policy.py pre") and pre_h[0]["fail_closed"] is True)
        self.assertEqual(pre_h[1]["command"], "/eigener/hook.sh")   # eigener Hook bleibt
        self.assertTrue(data["hooks"]["post_tool_call"][0]["command"].endswith("nuorb_policy.py post"))
        self.assertFalse(jc.apply_tools_policy(data, "narrow"))   # zweiter Lauf ändert nichts

    def test_erweitert(self):
        data: dict = {}
        jc.apply_tools_policy(data, "extended")
        self.assertEqual(data["platform_toolsets"]["api_server"], ["hermes-api-server"])
        self.assertEqual(len(data["hooks"]["pre_tool_call"]), 1)   # Regeln gelten auch erweitert

    def test_allowlist_nur_fuer_die_eigenen_hooks(self):
        jc.allow_policy_hooks(T)
        jc.allow_policy_hooks(T)
        d = json.loads((T / "shell-hooks-allowlist.json").read_text())
        self.assertEqual(sorted(e["event"] for e in d["approvals"]), ["post_tool_call", "pre_tool_call"])

    def test_zustand_ohne_datei_ist_eng(self):
        self.assertEqual(jc.tools_state()["mode"], "narrow")


if __name__ == "__main__":
    unittest.main()
