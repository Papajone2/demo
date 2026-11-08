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
    def test_arm_smoke_invokes_python_directly_without_binfmt_dependency(self):
        script = (ROOT / "board/post-build.sh").read_text()
        self.assertIn('chroot "$target" /usr/bin/qemu-arm-static \\\n  /usr/bin/python3', script)
        self.assertNotIn("/usr/bin/env PYTHONPATH", script)

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
            config.write_text(text.replace("CONFIG_EXT4_FS=y", "# CONFIG_EXT4_FS is not set"))
            with self.assertRaises(SystemExit):
                verify(temp)

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
