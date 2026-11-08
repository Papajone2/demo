"""Startup/asset regression checks; not a physical Pi boot-time measurement."""
import ast
from pathlib import Path
import unittest
import tempfile
import importlib.util
import subprocess
import sys
from unittest.mock import patch, mock_open

from satooshi.oled import OLED
from satooshi.screen import Screen
from satooshi import splash


ROOT = Path(__file__).resolve().parents[1]


class BootTests(unittest.TestCase):
    def test_early_splash_shows_real_home_and_leaves_display_on(self):
        expected = OLED.frame_bytes(Screen().render(("SATOOSHI LOGO", [], ""), phase="home"))
        with patch.object(splash, "OLED") as oled, \
                patch("builtins.open", mock_open(read_data=expected)):
            splash.run()
            actual = oled.return_value.show_bytes.call_args.args[0]
            self.assertEqual(expected, actual)
            oled.return_value.close.assert_called_once_with(blank=False)

    def test_early_splash_retries_i2c_without_sleeping_on_success(self):
        with patch.object(splash, "OLED", side_effect=[OSError(), unittest.mock.Mock()]), \
                patch("builtins.open", mock_open(read_data=b"\xff" * 1024)), \
                patch.object(splash.time, "sleep") as sleep:
            splash.run()
            sleep.assert_called_once_with(0.1)

    def test_splash_has_no_secret_or_signing_dependencies(self):
        tree = ast.parse((ROOT / "device/satooshi/splash.py").read_text())
        names = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        self.assertEqual(names, ["oled", "boot_timing"])

    def test_cold_splash_import_does_not_load_image_or_crypto_libraries(self):
        subprocess.run([sys.executable, "-c",
            "import sys; sys.path.insert(0, sys.argv[1]); import satooshi.splash; "
            "assert not any(n.split('.')[0] in ('PIL','ecdsa','cryptography','mnemonic','embit') "
            "for n in sys.modules)",
            str(ROOT / "device")], check=True)

    def test_splash_rejects_invalid_compiled_frame_before_touching_display(self):
        with patch("builtins.open", mock_open(read_data=b"invalid")), patch.object(splash, "OLED") as oled:
            with self.assertRaises(ValueError):
                splash.run()
            oled.assert_not_called()

    def test_oled_rejects_short_or_oversized_frame(self):
        oled = OLED.__new__(OLED)
        oled.command = unittest.mock.Mock()
        for size in (0, 1023, 1025):
            with self.assertRaises(ValueError):
                oled.show_bytes(bytes(size))
        oled.command.assert_not_called()

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
        self.assertIn("After=systemd-remount-fs.service systemd-modules-load.service\n", main)
        self.assertIn("RequiresMountsFor=/opt/satooshi/device /var/lib/satooshi", main)
        self.assertNotIn("Wants=local-fs.target", main)
        self.assertNotIn("After=local-fs.target systemd-modules-load.service satooshi-usb.service", main)
        self.assertNotIn("After=satooshi-splash.service", main)
        splash_unit = (ROOT / "image/satooshi-splash.service").read_text()
        self.assertNotIn("local-fs.target", splash_unit)
        self.assertIn("RequiresMountsFor=/opt/satooshi/device", splash_unit)
        usb = (ROOT / "image/satooshi-usb.service").read_text()
        self.assertNotIn("satooshi.service", usb)
        self.assertNotIn("local-fs.target", usb)
        self.assertIn("systemd-remount-fs.service", usb)

    def test_boot_report_is_delayed_and_only_collects_public_stages(self):
        timer = (ROOT / "image/satooshi-boot-report.timer").read_text()
        report = (ROOT / "image/boot-report.sh").read_text()
        self.assertIn("OnBootSec=60s", timer)
        self.assertIn("SATOOSHI_BOOT stage=", report)
        self.assertIn("not since power-on", report)
        for sensitive in ("/var/lib/satooshi", "vault.json", "/etc/machine-id"):
            self.assertNotIn(sensitive, report)

    def test_boot_markers_accept_only_public_fixed_stages(self):
        from satooshi.boot_timing import mark
        with self.assertRaises(ValueError):
            mark("arbitrary data")
        with patch("builtins.print") as output:
            mark("wallet_ready")
            self.assertRegex(output.call_args.args[0], r"^SATOOSHI_BOOT stage=wallet_ready kernel_seconds=\d+\.\d{3}$")

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
        self.assertIn('assets/splash.bin', source)


class BootConfigTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("boot_optimizer", ROOT / "image/optimize-boot.py")
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.boot = self.root / "boot/firmware"
        self.boot.mkdir(parents=True)
        (self.root / "etc").mkdir()
        (self.root / "lib/modules/6.12-test-rpi-v6").mkdir(parents=True)
        (self.boot / "config.txt").write_text("[all]\nauto_initramfs=1\n")
        (self.boot / "cmdline.txt").write_text("root=PARTUUID=example-02 rootfstype=ext4 rootwait\n")
        (self.root / "etc/fstab").write_text("PARTUUID=example-02 / ext4 defaults 0 1\n")
        self.kernel = self.root / "boot/config-6.12-test-rpi-v6"
        self.flags = ["CONFIG_MMC=y", "CONFIG_MMC_BLOCK=y", "CONFIG_EXT4_FS=y",
                      "CONFIG_DEVTMPFS=y", "CONFIG_DEVTMPFS_MOUNT=y",
                      "CONFIG_MMC_BCM2835=y"]

    def test_keeps_initramfs_without_positive_kernel_evidence(self):
        self.assertTrue(self.module.optimize(self.root).startswith("kept:"))
        self.assertNotIn("auto_initramfs=0", (self.boot / "config.txt").read_text())

    def test_headless_oled_profile_preserves_storage_and_randomness(self):
        (self.boot / "config.txt").write_text("[all]\n\ndtoverlay=vc4-kms-v3d\n")
        original = "console=tty1 root=PARTUUID=example-02 rootfstype=ext4 rootwait fsck.repair=yes\n"
        (self.boot / "cmdline.txt").write_text(original)
        self.module.optimize(self.root)
        config = (self.boot / "config.txt").read_text()
        self.assertIn("# Satooshi I2C-only display: dtoverlay=vc4-kms-v3d", config)
        self.assertFalse(any(line.lstrip().startswith("dtoverlay=vc4-") for line in config.splitlines()))
        self.assertIn("max_framebuffers=0", config)
        self.assertIn("dtparam=audio=off", config)
        self.assertNotIn("gpu_mem=16", config)
        arguments = (self.boot / "cmdline.txt").read_text().split()
        for retained in ("root=PARTUUID=example-02", "rootfstype=ext4", "rootwait", "fsck.repair=yes"):
            self.assertIn(retained, arguments)
        self.assertNotIn("console=tty1", arguments)
        self.assertIn("quiet", arguments)
        self.assertNotIn("random.trust_cpu=on", arguments)

    def test_cutdown_firmware_requires_matching_files_and_no_override(self):
        for name in ("start_cd.elf", "fixup_cd.dat"):
            (self.boot / name).write_bytes(b"firmware-fixture")
        self.module.optimize(self.root)
        self.assertIn("gpu_mem=16", (self.boot / "config.txt").read_text())
        (self.boot / "config.txt").write_text("[all]\nstart_file=custom.elf\n")
        self.module.optimize(self.root)
        self.assertNotIn("gpu_mem=16", (self.boot / "config.txt").read_text())

    def test_headless_profile_and_console_flags_are_idempotent(self):
        self.module.optimize(self.root)
        self.module.optimize(self.root)
        self.assertEqual((self.boot / "config.txt").read_text().count("# BEGIN SATOOSHI HEADLESS"), 1)
        arguments = (self.boot / "cmdline.txt").read_text().split()
        self.assertEqual(arguments.count("quiet"), 1)
        self.assertEqual(arguments.count("loglevel=3"), 1)

    def test_explicit_initramfs_line_is_commented_even_after_blank_lines(self):
        self.kernel.write_text("\n".join(self.flags))
        (self.boot / "config.txt").write_text("[all]\n\ninitramfs initramfs.img followkernel\n")
        self.module.optimize(self.root)
        config = (self.boot / "config.txt").read_text()
        self.assertFalse(any(line.lstrip().startswith("initramfs ") for line in config.splitlines()))
        self.assertIn("# Satooshi bypass: initramfs initramfs.img followkernel", config)

    def test_bypasses_only_with_all_builtin_root_requirements(self):
        self.kernel.write_text("\n".join(self.flags))
        self.assertTrue(self.module.optimize(self.root).startswith("bypassed:"))
        self.assertIn("auto_initramfs=0", (self.boot / "config.txt").read_text())
        self.assertIn("0 1", (self.root / "etc/fstab").read_text())  # fsck retained

    def test_keeps_initramfs_if_ext4_or_sd_driver_is_modular(self):
        for flag in ("CONFIG_EXT4_FS", "CONFIG_MMC_BCM2835"):
            self.kernel.write_text("\n".join(self.flags).replace(flag + "=y", flag + "=m"))
            self.assertTrue(self.module.optimize(self.root).startswith("kept:"))

    def test_keeps_initramfs_for_ambiguous_kernel_or_non_ext4_root(self):
        self.kernel.write_text("\n".join(self.flags))
        for config in ("include custom.txt", "kernel=custom.img", "os_prefix=alternate/"):
            (self.boot / "config.txt").write_text("[all]\n" + config + "\n")
            self.assertTrue(self.module.optimize(self.root).startswith("kept:"))
        (self.boot / "config.txt").write_text("[all]\n")
        (self.root / "etc/fstab").write_text("/dev/mapper/cryptroot / ext4 defaults 0 1")
        self.assertTrue(self.module.optimize(self.root).startswith("kept:"))


if __name__ == "__main__":
    unittest.main()
