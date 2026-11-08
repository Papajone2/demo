"""Restart and public loading regressions; entropy is a fixed test fixture."""
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
from satooshi.controller import Controller
from satooshi.vault import Vault
from satooshi.screen import Screen

class SessionBootTests(unittest.TestCase):
    def test_pin_is_required_again_after_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            vault = Vault(directory)
            vault.create(bytes(range(32)), "12")
            first = Controller(vault, lambda event: None)
            self.assertIsNone(first.entropy)
            self.assertEqual((first.phase, first.pin_mode), ("pin", "unlock"))
            first.digit, first.pin = 7, "1"
            first.request("hello", {}, "hello")
            first.request("unlock", {}, "unlock")
            self.assertEqual((first.phase, first.digit, first.pin), ("pin", 7, "1"))
            first.pin = "12"
            first._finish_pin()
            self.assertEqual(first.entropy, bytes(range(32)))
            second = Controller(vault, lambda event: None)
            self.assertIsNone(second.entropy)
            self.assertEqual(second.phase, "pin")
            self.assertEqual(second.status()["confirmHoldMs"], 300)

    def test_loading_is_distinct_from_idle(self):
        screen = Screen()
        loading = screen.render(("SATOOSHI LOGO", [], ""), phase="loading")
        idle = screen.render(("SATOOSHI START", [], ""), phase="home")
        self.assertEqual(loading.size, (128, 64))
        self.assertNotEqual(loading.tobytes(), idle.tobytes())

    def test_controller_import_defers_heavy_signers(self):
        device = str(Path(__file__).resolve().parents[1] / "device")
        subprocess.run([sys.executable, "-c",
            "import sys; sys.path.insert(0, sys.argv[1]); import satooshi.controller; "
            "assert 'cryptography.hazmat.primitives.ciphers.aead' not in sys.modules; "
            "assert 'ecdsa' not in sys.modules", device], check=True)
