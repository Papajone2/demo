"""Execute public diagnostic collection against an isolated fake command set."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

class BootReportTests(unittest.TestCase):
    def test_report_filters_private_lines_and_copies_only_public_usb_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            boot, tools = root / "boot", root / "tools"
            boot.mkdir()
            tools.mkdir()
            commands = {
                "mountpoint": "exit 0",
                "journalctl": "printf '%s\\n' '   8.400 SATOOSHI_BOOT stage=wallet_ready kernel_seconds=8.400' 'do-not-log-sensitive-fixture'",
                "systemctl": "printf '%s\\n' 'Id=satooshi.service' 'ExecMainStartTimestampMonotonic=7000000'",
                "systemd-analyze": "printf '%s\\n' 'Synthetic boot summary'",
            }
            for name, body in commands.items():
                target = tools / name
                target.write_text("#!/bin/sh\n" + body + "\n")
                target.chmod(0o755)
            usb = root / "usb-status.txt"
            usb.write_text("stage=serial_ready\nexit_code=0\n")
            source = (Path(__file__).parents[1] / "image/boot-report.sh").read_text()
            source = source.replace("/boot/firmware", str(boot))
            source = source.replace("/run/satooshi-usb-status.txt", str(usb))
            script = root / "report.sh"
            script.write_text(source)
            subprocess.run(["sh", str(script)], check=True,
                           env={**os.environ, "PATH": str(tools) + ":" + os.environ["PATH"]})
            report = (boot / "satooshi-boot-status.txt").read_text()
            self.assertIn("kernel_seconds=8.400", report)
            self.assertIn("not since power-on", report)
            self.assertIn("stage=serial_ready", report)
            self.assertNotIn("do-not-log-sensitive-fixture", report)
            self.assertEqual((boot / "satooshi-usb-status.txt").read_text(), usb.read_text())
            self.assertFalse(list(boot.glob(".satooshi-boot-status.*")))
