"""Offline checks for the portal parser and account-switch lifecycle."""

import importlib.util
import io
import json
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

try:
    import fcntl  # noqa: F401
except ImportError:
    sys.modules["fcntl"] = types.SimpleNamespace(flock=lambda *_: None, LOCK_EX=2)

MODULE = Path(__file__).resolve().parents[1] / "manager.py"
spec = importlib.util.spec_from_file_location("manager", MODULE)
manager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manager)

OFFLINE = "<script>v4serip='172.30.201.2';</script>"
ONLINE = "<script>time='18';uid='test-user';</script>"


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        patches = [
            mock.patch.object(manager, "BASE", base),
            mock.patch.object(manager, "CONFIG", base / "accounts.json"),
            mock.patch.object(manager, "LOCK", base / "lock"),
            mock.patch.object(manager.time, "sleep"),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def run_command(self, *args):
        with mock.patch.object(sys, "argv", ["manager.py", *args]), redirect_stdout(io.StringIO()):
            return manager.main()

    def test_portal_state_parsing(self):
        with mock.patch.object(manager, "fetch", return_value=ONLINE):
            self.assertEqual(manager.state()[0], "online")
        with mock.patch.object(manager, "fetch", return_value=OFFLINE):
            self.assertEqual(manager.state()[0], "offline")
        with mock.patch.object(manager, "fetch", return_value="unexpected page"):
            self.assertEqual(manager.state()[0], "unknown")

    def test_switch_then_online_check_does_not_relogin(self):
        manager.save({"accounts": {"second": {"user": "test-user", "password": "test-secret"}},
                      "active": None, "enabled": False})
        responses = [OFFLINE, OFFLINE, "successfully logged", ONLINE]
        with mock.patch.object(manager, "fetch", side_effect=responses) as fetch:
            self.assertEqual(self.run_command("use", "second"), 0)
            self.assertEqual(fetch.call_count, 4)
        config = json.loads(manager.CONFIG.read_text(encoding="utf-8"))
        self.assertEqual(config["active"], "second")
        self.assertTrue(config["enabled"])
        with mock.patch.object(manager, "fetch", return_value=ONLINE) as fetch:
            self.assertEqual(self.run_command("check"), 0)
            self.assertEqual(fetch.call_count, 1)

    def test_logout_disables_automatic_login(self):
        manager.save({"accounts": {"main": {"user": "test-user", "password": "test-secret"}},
                      "active": "main", "enabled": True})
        with mock.patch.object(manager, "fetch", side_effect=[ONLINE, "Msg=14", OFFLINE]):
            self.assertEqual(self.run_command("logout"), 0)
        config = json.loads(manager.CONFIG.read_text(encoding="utf-8"))
        self.assertFalse(config["enabled"])


if __name__ == "__main__":
    unittest.main()
