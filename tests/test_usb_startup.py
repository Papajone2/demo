"""Configfs control-flow simulation, not a physical USB/boot test."""
import pathlib
import subprocess
import tempfile
import unittest


class UsbStartupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.gadget = self.root / "gadget"
        self.gadget.mkdir()
        # sysfs can report a nonzero stat size for an unbound/empty attribute.
        (self.gadget / "UDC").write_text("\n")
        self.controllers = self.root / "controllers"
        self.controllers.mkdir()
        (self.controllers / "test.usb").mkdir()
        self.boot = self.root / "boot"
        self.boot.mkdir()
        self.tty = self.root / "ttyGS0"
        self.tty.touch()
        source = (pathlib.Path(__file__).parents[1] / "image/usb-gadget.sh").read_text()
        source = source.replace("/sys/kernel/config/usb_gadget/satooshi", str(self.gadget))
        source = source.replace("/sys/kernel/config", str(self.root / "configfs"))
        source = source.replace("/sys/class/udc", str(self.controllers))
        source = source.replace("/boot/firmware", str(self.boot))
        source = source.replace("/dev/ttyGS0", str(self.tty)).replace("[[ -c ", "[[ -f ")
        # Never mount, change ownership or load modules on the test host.
        mocks = "\nmodprobe(){ :; }; mountpoint(){ return 0; }; sleep(){ :; }; chown(){ :; }; chmod(){ :; };\n"
        self.script = self.root / "run.sh"
        self.script.write_text(source.replace("set -euo pipefail", "set -euo pipefail" + mocks, 1))

    def run_script(self):
        return subprocess.run(["bash", str(self.script)], capture_output=True, text=True, timeout=30)

    def test_partial_unbound_gadget_is_configured_not_mistaken_for_ready(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.gadget / "UDC").read_text().strip(), "test.usb")
        self.assertEqual((self.gadget / "idVendor").read_text().strip(), "0x1d6b")
        self.assertTrue((self.gadget / "configs/c.1/acm.usb0").is_symlink())
        report = (self.boot / "satooshi-usb-status.txt").read_text()
        self.assertIn("stage=serial_ready", report)
        self.assertIn("exit_code=0", report)
        self.assertIn("serial_node=present", report)

    def test_bound_gadget_reentry_preserves_configuration(self):
        self.assertEqual(self.run_script().returncode, 0)
        (self.gadget / "idVendor").write_text("existing configuration\n")
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.gadget / "idVendor").read_text(), "existing configuration\n")

    def test_missing_controller_reports_failure_not_success(self):
        (self.controllers / "test.usb").rmdir()
        self.tty.unlink()
        result = self.run_script()
        self.assertEqual(result.returncode, 1, result.stderr)
        report = (self.boot / "satooshi-usb-status.txt").read_text()
        self.assertIn("stage=wait_for_controller", report)
        self.assertIn("exit_code=1", report)
        self.assertIn("serial_node=absent", report)
