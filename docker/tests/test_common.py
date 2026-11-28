"""Unit-Tests für docker/app/nuorb_common.py: Kopplungscodes, Geräte-Token, Widerruf, Dateirechte."""
from __future__ import annotations

import stat
import time
import unittest

from _lade import APP, lade, temp_ordner

T = temp_ordner("common")
jc = lade("nuorb_common_test", APP / "nuorb_common.py", {"HERMES_HOME": str(T), "NUORB_MODELS": str(T / "models")})


class Kopplung(unittest.TestCase):
    def neuer_code(self) -> str:
        return jc.new_pairing_code("test")["code"]

    def test_code_einmalig(self):
        code = self.neuer_code()
        self.assertTrue(jc.redeem_pairing_code(code))
        self.assertFalse(jc.redeem_pairing_code(code))

    def test_falscher_code(self):
        self.assertFalse(jc.redeem_pairing_code("AAAA-AAAA"))
        self.assertFalse(jc.redeem_pairing_code(""))

    def test_abgelaufener_code(self):
        code = self.neuer_code()
        data = jc._read_json(jc.PAIRING, {})
        for v in data.values():
            v["exp"] = time.time() - 1
        jc._write_json(jc.PAIRING, data)
        self.assertFalse(jc.redeem_pairing_code(code))

    def test_dateien_nur_fuer_den_besitzer(self):
        self.neuer_code()
        jc.add_device("Test", "android", "192.168.1.60")
        for p in (jc.PAIRING, jc.DEVICES):
            with self.subTest(p=p.name):
                self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o600)


class Geraete(unittest.TestCase):
    def test_token_gilt_und_wird_nur_als_hash_gespeichert(self):
        did, token = jc.add_device("Handy", "android", "192.168.1.61")
        self.assertEqual(jc.device_for_token(token, "192.168.1.61"), did)
        self.assertNotIn(token, jc.DEVICES.read_text())

    def test_widerruf(self):
        did, token = jc.add_device("Weg", "android", "192.168.1.62")
        self.assertTrue(jc.revoke_device(did))
        self.assertIsNone(jc.device_for_token(token))
        self.assertFalse(jc.revoke_device(did))

    def test_unsinnige_token(self):
        self.assertIsNone(jc.device_for_token(""))
        self.assertIsNone(jc.device_for_token("x" * 500))
        self.assertIsNone(jc.device_for_token("falsch"))


if __name__ == "__main__":
    unittest.main()
