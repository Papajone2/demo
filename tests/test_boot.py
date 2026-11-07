"""Startup/asset regression checks; not a physical Pi boot-time measurement."""
import ast
from pathlib import Path
import unittest
from unittest.mock import patch

from satooshi.oled import OLED
from satooshi.screen import Screen
from satooshi import splash


ROOT = Path(__file__).resolve().parents[1]


class BootTests(unittest.TestCase):
    def test_early_splash_shows_real_home_and_leaves_display_on(self):
        with patch.object(splash, "OLED") as oled:
            splash.run()
            expected = Screen().render(("SATOOSHI LOGO", [], ""), phase="home")
            actual = oled.return_value.show.call_args.args[0]
            self.assertEqual(expected.tobytes(), actual.tobytes())
            oled.return_value.close.assert_called_once_with(blank=False)

    def test_early_splash_retries_i2c_without_sleeping_on_success(self):
        with patch.object(splash, "OLED", side_effect=[OSError(), unittest.mock.Mock()]), \
                patch.object(splash.time, "sleep") as sleep:
            splash.run()
            sleep.assert_called_once_with(0.1)

    def test_splash_has_no_secret_or_signing_dependencies(self):
        tree = ast.parse((ROOT / "device/satooshi/splash.py").read_text())
        names = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        self.assertEqual(names, ["oled", "screen"])

    def test_wordmark_is_bounded_one_bit_and_not_empty(self):
        logo = Screen().wordmark
        self.assertEqual(logo.mode, "1")
        self.assertLessEqual(logo.width, 124)
        self.assertLessEqual(logo.height, 26)
        self.assertIsNotNone(logo.getbbox())

    def test_early_services_do_not_wait_for_wallet_or_network(self):
        for name in ("satooshi-usb", "satooshi-splash"):
            unit = (ROOT / f"image/{name}.service").read_text()
            self.assertIn("DefaultDependencies=no", unit)
            self.assertIn("WantedBy=sysinit.target", unit)
            self.assertNotIn("network-online.target", unit)
        main = (ROOT / "image/satooshi.service").read_text()
        self.assertIn("DefaultDependencies=no", main)
        self.assertIn("WantedBy=sysinit.target", main)
        self.assertIn("After=local-fs.target systemd-modules-load.service satooshi-usb.service", main)
        self.assertNotIn("After=satooshi-splash.service", main)

    def test_splash_close_keeps_pixels_without_poweroff_command(self):
        oled = OLED.__new__(OLED)
        oled.bus = unittest.mock.Mock()
        oled.command = unittest.mock.Mock()
        oled.close(blank=False)
        oled.command.assert_not_called()
        oled.bus.close.assert_called_once()

    def test_build_validates_installed_firmware_and_unique_filename(self):
        source = (ROOT / "image/build.sh").read_text()
        self.assertIn('build-${GITHUB_RUN_NUMBER:-local}-${COMMIT:0:8}.img', source)
        self.assertIn('status["buildCommit"] == os.environ["EXPECTED_COMMIT"]', source)
        self.assertIn('satooshi-build.json', source)


if __name__ == "__main__":
    unittest.main()
