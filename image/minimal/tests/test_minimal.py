"""Host-only contract tests. No kernel compilation, devices or wallet secrets."""
import importlib.util
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


class MinimalTests(unittest.TestCase):
    def test_full_system_boot_check_exercises_actual_sandbox_without_secrets(self):
        checker = module("sandbox_boot", ROOT / "board/check-sandbox-boot.py")
        launcher = (ROOT / "board/overlay/usr/sbin/satooshi-run").read_text()
        probe_launcher = checker.launcher_for_probe(launcher)
        self.assertNotIn("-m satooshi.main", probe_launcher)
        for protection in ("--no-new-privs", "--unshare-net", "--cap-drop ALL",
                           "--reuid=1000", "--ro-bind / /"):
            self.assertIn(protection, probe_launcher)
        with self.assertRaises(SystemExit):
            checker.launcher_for_probe(launcher.replace("-m satooshi.main", "-m changed"))
        compile(checker.PROBE, "<sandbox-probe>", "exec")
        self.assertIn("127.0.0.1", checker.PROBE)
        self.assertIn("errno.ENETUNREACH", checker.PROBE)
        self.assertIn("getuid() == 1000", checker.PROBE)
        self.assertIn("NoNewPrivs", checker.PROBE)
        self.assertIn('check-sandbox-boot.py', (ROOT / "board/post-image.sh").read_text())

    def test_offline_wallet_sandbox_requires_ipv4_loopback(self):
        fragment = (ROOT / "board/kernel.fragment").read_text().splitlines()
        self.assertIn("CONFIG_INET=y", fragment)
        self.assertIn("CONFIG_NET_NS=y", fragment)
        launcher = (ROOT / "board/overlay/usr/sbin/satooshi-run").read_text()
        self.assertIn("--unshare-net", launcher)
        self.assertLess(launcher.index("exec >>/run/wallet.log"),
                        launcher.index("test -f /run/storage-ready"))
        self.assertIn("stage=launcher_failed", launcher)
        verify = module("verify_ipv4", ROOT / "board/verify-kernel.py").verify
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "linux-test/.config"
            path.parent.mkdir()
            path.write_text("\n".join(fragment) + "\n")
            verify(temp)
            path.write_text(path.read_text().replace("CONFIG_INET=y", "# CONFIG_INET is not set"))
            with self.assertRaises(SystemExit) as error:
                verify(temp)
            self.assertIn("CONFIG_INET=y", str(error.exception))

    def test_optional_modules_are_disabled_before_kconfig_not_promoted(self):
        prepare = module("prepare_kernel", ROOT / "board/prepare-kernel.py").prepare
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bcmrpi_defconfig"
            path.write_text("CONFIG_BOARD=y\nCONFIG_OPTIONAL=m\n# CONFIG_OLD is not set\n")
            self.assertEqual(prepare(path), 1)
            self.assertEqual(path.read_text(),
                             "CONFIG_BOARD=y\n# CONFIG_OPTIONAL is not set\n# CONFIG_OLD is not set\n")
            self.assertEqual(prepare(path), 0)
        hooks = (ROOT / "linux/early-logo.mk").read_text()
        self.assertIn("LINUX_POST_PATCH_HOOKS += SATOOSHI_TRIM_DISTRO_KERNEL", hooks)
        self.assertIn('arch/arm/configs/bcmrpi_defconfig', hooks)

    def test_kernel_serial_readiness_and_missing_controller_fail_explicitly(self):
        import os
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            udc = root / "sys/class/udc/controller"
            udc.mkdir(parents=True)
            (udc / "function").write_text("Gadget Serial v2.4\n")
            (udc / "state").write_text("configured\n")
            (root / "dev").mkdir()
            (root / "dev/ttyGS0").symlink_to("/dev/null")
            (root / "proc").mkdir()
            (root / "proc/uptime").write_text("2.50 0.00\n")
            env = dict(os.environ, SATOOSHI_USB_SYS_ROOT=str(root / "sys"),
                       SATOOSHI_USB_DEV_ROOT=str(root / "dev"),
                       SATOOSHI_USB_PROC_ROOT=str(root / "proc"),
                       SATOOSHI_USB_MAX_TRIES="1")
            command = ["sh", str(ROOT / "board/minimal-usb.sh")]
            result = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("stage=usb_bound kernel_seconds=2.50", result.stdout)
            self.assertIn("Host link state: configured", result.stdout)
            (root / "dev/ttyGS0").unlink()
            result = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("USB serial unavailable", result.stdout)
        script = (ROOT / "board/minimal-usb.sh").read_text()
        self.assertNotIn("mount -t configfs", script)
        self.assertNotIn("usb_gadget/", script)

    def test_packaged_boot_files_include_chrome_serial_identity(self):
        verify = module("verify_boot", ROOT / "board/verify-boot.py").verify
        with tempfile.TemporaryDirectory() as temp:
            images = Path(temp)
            firmware = images / "rpi-firmware"
            (firmware / "overlays").mkdir(parents=True)
            (firmware / "config.txt").write_text((ROOT / "board/config.txt").read_text())
            (firmware / "cmdline.txt").write_text((ROOT / "board/cmdline.txt").read_text())
            for relative in ("rpi-firmware/bootcode.bin", "rpi-firmware/start_cd.elf",
                             "rpi-firmware/fixup_cd.dat", "rpi-firmware/overlays/dwc2.dtbo",
                             "bcm2708-rpi-zero-w.dtb", "zImage"):
                (images / relative).write_bytes(b"fixture")
            verify(images)
            (firmware / "cmdline.txt").write_text("root=/dev/mmcblk0p2\n")
            with self.assertRaises(SystemExit):
                verify(images)
            (firmware / "cmdline.txt").write_text((ROOT / "board/cmdline.txt").read_text())
            (firmware / "overlays/dwc2.dtbo").unlink()
            with self.assertRaises(SystemExit):
                verify(images)

    def test_directly_executed_hooks_and_startup_scripts_are_executable(self):
        import os
        for relative in ("board/post-build.sh", "board/post-image.sh",
                         "board/overlay/etc/init.d/rcS", "board/overlay/etc/init.d/rcK",
                         "board/overlay/usr/sbin/satooshi-run"):
            path = ROOT / relative
            self.assertTrue(os.access(path, os.X_OK), f"Missing execute bit: {relative}")
            self.assertTrue(path.read_text().startswith("#!"), f"Missing interpreter: {relative}")

    def test_arm_smoke_invokes_python_directly_without_binfmt_dependency(self):
        script = (ROOT / "board/post-build.sh").read_text()
        self.assertIn('chroot "$target" /usr/bin/qemu-arm-static \\\n  /usr/bin/python3', script)
        self.assertNotIn("/usr/bin/env PYTHONPATH", script)

    def test_gpio_abi_check_loads_native_extension_not_python_wrapper(self):
        import ast
        from types import SimpleNamespace
        from unittest.mock import Mock
        tree = ast.parse((ROOT / "board/target-smoke.py").read_text())
        start = next(i for i, node in enumerate(tree.body)
                     if isinstance(node, ast.Assign)
                     and isinstance(node.targets[0], ast.Name)
                     and node.targets[0].id == "gpio")
        block = compile(ast.Module(body=tree.body[start:start + 3], type_ignores=[]),
                        "<gpio-abi-check>", "exec")
        origin = "/fixture/RPi/_GPIO.cpython-312-arm-linux-gnueabihf.so"
        spec = SimpleNamespace(origin=origin,
                               loader=importlib.machinery.ExtensionFileLoader("RPi._GPIO", origin))
        find_spec = Mock(return_value=spec)
        cdll = Mock()
        namespace = {
            "importlib": SimpleNamespace(util=SimpleNamespace(find_spec=find_spec),
                                        machinery=importlib.machinery),
            "ctypes": SimpleNamespace(CDLL=cdll),
        }
        exec(block, namespace)
        find_spec.assert_called_once_with("RPi._GPIO")
        cdll.assert_called_once_with(origin)
        # Reject a Python wrapper even if a future refactor resolves that instead.
        spec.loader = importlib.machinery.SourceFileLoader("RPi.GPIO", "/fixture/__init__.py")
        cdll.reset_mock()
        with self.assertRaises(AssertionError):
            exec(block, namespace)
        cdll.assert_not_called()

    def test_rust_manifest_preflight_rejects_newer_editions_and_msrv(self):
        check = module("check_rust", ROOT / "check-rust.py").check
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(SystemExit):
                check(temp)
            path = Path(temp) / "fixture/Cargo.toml"
            path.parent.mkdir()
            path.write_text('[package]\nname="fixture"\nversion="1.0.0"\nedition="2021"\nrust-version="1.60"\n')
            check(temp)
            path.write_text(path.read_text().replace('edition="2021"', 'edition="2024"'))
            with self.assertRaises(SystemExit):
                check(temp)
            path.write_text('[package]\nname="fixture"\nversion="1.0.0"\nrust-version="1.85"\n')
            with self.assertRaises(SystemExit):
                check(temp)
        workflow = (ROOT / "build-minimal-image.yml").read_text()
        self.assertIn("cargo +1.82.0 build --locked", workflow)

    def test_embit_extract_hook_keeps_only_armv6_and_requires_it(self):
        recipe = ROOT / "package/python-embit/python-embit.mk"
        with tempfile.TemporaryDirectory() as temp:
            package = Path(temp) / "source"
            libraries = package / "src/embit/util/prebuilt"
            libraries.mkdir(parents=True)
            keep = "libsecp256k1_linux_armv6l.so"
            for name in (keep, "libsecp256k1_linux_armv7l.so",
                         "libsecp256k1_linux_aarch64.so",
                         "libsecp256k1_linux_x86_64.so",
                         "libsecp256k1_darwin_arm64.dylib",
                         "libsecp256k1_windows_amd64.dll"):
                (libraries / name).write_bytes(b"fixture")
            makefile = (
                f"include {recipe}\n"
                f"{package}/check:\n"
                "\t$(call PYTHON_EMBIT_KEEP_ARMV6_LIBRARY)\n"
            )
            def run():
                return subprocess.run(
                    ["make", "--no-print-directory", "-f", "-", f"{package}/check"],
                    input=makefile, text=True, capture_output=True,
                )
            result = run()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual([p.name for p in libraries.iterdir()], [keep])
            self.assertEqual(run().returncode, 0)
            (libraries / keep).unlink()
            self.assertNotEqual(run().returncode, 0)
        self.assertIn("PYTHON_EMBIT_POST_EXTRACT_HOOKS += PYTHON_EMBIT_KEEP_ARMV6_LIBRARY",
                      recipe.read_text())

    def test_kernel_requires_all_critical_builtin_drivers(self):
        verify = module("verify_kernel", ROOT / "board/verify-kernel.py").verify
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "linux-fixture/.config"
            config.parent.mkdir()
            text = (ROOT / "board/kernel.fragment").read_text()
            config.write_text(text)
            verify(temp)
            config.write_text(text.replace("# CONFIG_USB_DWCOTG is not set",
                                          "CONFIG_USB_DWCOTG=y"))
            with self.assertRaises(SystemExit):
                verify(temp)
            config.write_text(text.replace("CONFIG_EXT4_FS=y", "# CONFIG_EXT4_FS is not set"))
            with self.assertRaises(SystemExit):
                verify(temp)
            config.write_text(text.replace("CONFIG_RASPBERRYPI_GPIOMEM=y",
                                          "CONFIG_BCM2835_DEVGPIOMEM=y"))
            with self.assertRaises(SystemExit):
                verify(temp)
            config.write_text(text)
            result = subprocess.run(
                ["python3", str(ROOT / "board/verify-kernel.py"), "--config-only", temp],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("LINUX_POST_CONFIGURE_HOOKS += SATOOSHI_VERIFY_KERNEL_CONFIG",
                      (ROOT / "linux/early-logo.mk").read_text())

    def test_mbr_and_ext4_validation_rejects_corruption(self):
        verify = module("verify_image", ROOT / "board/verify-image.py").verify
        with tempfile.TemporaryDirectory() as temp:
            image = Path(temp) / "test.img"
            data = bytearray(128 * 512)
            data[510:512] = b"\x55\xaa"
            for index, kind in enumerate((0x0C, 0x83, 0x83)):
                start = 8 + index * 32
                offset = 446 + index * 16
                data[offset + 4] = kind
                struct.pack_into("<II", data, offset + 8, start, 32)
                if index:
                    data[start * 512 + 1080:start * 512 + 1082] = b"\x53\xef"
            image.write_bytes(data)
            verify(image)
            data[510] = 0
            image.write_bytes(data)
            with self.assertRaises(SystemExit):
                verify(image)

    def test_no_automatic_format_or_security_shortcuts(self):
        startup = (ROOT / "board/overlay/etc/init.d/rcS").read_text()
        self.assertLess(startup.index("early-splash"), startup.index("e2fsck"))
        self.assertNotIn("mkfs", startup)
        self.assertIn("empty = true", (ROOT / "board/genimage.cfg").read_text())
        self.assertIn("exit 1", startup)
        launcher = (ROOT / "board/overlay/usr/sbin/satooshi-run").read_text()
        for protection in ("--no-new-privs", "--unshare-net", "--ro-bind / /",
                           "--tmpfs /tmp", "--cap-drop ALL", "--reuid=1000"):
            self.assertIn(protection, launcher)

    def test_no_network_services_or_console_login(self):
        init = (ROOT / "board/overlay/etc/inittab").read_text()
        self.assertNotIn("getty", init)
        self.assertNotIn("login", init)
        workflow = (ROOT / "build-minimal-image.yml").read_text()
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("  push:", workflow)
        self.assertIn("image/minimal/build.sh", workflow)

    def test_no_silent_missing_dependencies(self):
        check = module("check_config", ROOT / "check-config.py").check
        fragment = (ROOT / "configs/satooshi.fragment").read_text()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / ".config"
            path.write_text(fragment + "\nBR2_arm=y\nBR2_arm1176jzf_s=y\nBR2_TARGET_ROOTFS_EXT2_4=y\n")
            check(path)
            path.write_text(path.read_text().replace("BR2_PACKAGE_SATOOSHI_NATIVE=y", ""))
            with self.assertRaises(SystemExit):
                check(path)


if __name__ == "__main__":
    unittest.main()
