"""Public-logo generation and host-isolated kernel callback tests; no image build."""
from pathlib import Path
import importlib.util
import shutil
import subprocess
import tempfile
import unittest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class EarlyLogoTests(unittest.TestCase):
    def test_bitmap_is_centered_page_order_and_transparency_is_black(self):
        generator = load("logo", ROOT / "board/early-logo/make-logo.py")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "public.png"
            Image.new("RGBA", (40, 20), "white").save(source)
            frame = generator.frame_bytes(source)
            self.assertEqual(len(frame), 1024)
            self.assertEqual(frame[2 * 128 + 44], 0xc0)
            self.assertEqual(frame[3 * 128 + 44], 0xff)
            self.assertEqual(frame[5 * 128 + 44], 0x03)
            self.assertEqual(frame[0], 0)
            Image.new("RGBA", (40, 20), (255, 255, 255, 0)).save(source)
            self.assertFalse(any(generator.frame_bytes(source)))
            with self.assertRaises(ValueError):
                generator.generate(source, Path(directory) / "bad.h")

    def test_image_validation_requires_compiled_and_linked_arm_logo(self):
        check = load("kernel_logo", ROOT / "board/verify-kernel.py")
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(SystemExit):
                check.verify_logo(directory)
            kernel = Path(directory) / "linux-fixture"
            obj = kernel / "init/satooshi-bootlogo.o"
            obj.parent.mkdir(parents=True)
            header = bytearray(52)
            header[:6] = b"\x7fELF\x01\x01"
            header[18:20] = (40).to_bytes(2, "little")
            obj.write_bytes(header)
            with self.assertRaises(SystemExit):
                check.verify_logo(directory)
            (kernel / "System.map").write_text("00000000 t satooshi_early_logo_init\n")
            check.verify_logo(directory)
            header[18:20] = (62).to_bytes(2, "little")
            obj.write_bytes(header)
            with self.assertRaises(SystemExit):
                check.verify_logo(directory)

    def test_startup_keeps_early_frame_and_records_public_timing(self):
        startup = (ROOT / "board/overlay/etc/init.d/rcS").read_text()
        self.assertIn("/sys/kernel/satooshi_logo_ms", startup)
        self.assertIn("logo_kernel", startup)
        self.assertLess(startup.index("early-splash"), startup.index("minimal-usb.sh"))
        source = (ROOT / "board/early-logo/satooshi-bootlogo.c").read_text()
        self.assertIn("late_initcall_sync", source)
        self.assertIn("device_initcall_sync", source)
        self.assertIn("i2c_put_adapter", source)
        self.assertNotIn("msleep", source)
        self.assertNotIn("vault", source)
        self.assertIn("LINUX_PRE_BUILD_HOOKS +=", (ROOT / "linux/early-logo.mk").read_text())

    @unittest.skipUnless(shutil.which("cc"), "Host C compiler unavailable")
    def test_actual_c_success_disabled_missing_bus_and_failed_transfer(self):
        generator = load("logo_c", ROOT / "board/early-logo/make-logo.py")
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            linux = temp / "linux"
            linux.mkdir()
            (linux / "stubs.h").write_text(STUBS)
            for name in ("errno", "i2c", "init", "kobject", "ktime", "math64",
                         "printk", "string", "sysfs", "types", "timekeeping"):
                (linux / f"{name}.h").write_text('#include "stubs.h"\n')
            public = temp / "public.png"
            Image.new("RGBA", (40, 20), "white").save(public)
            generator.generate(public, temp / "satooshi-bootlogo-bitmap.h")
            source = ROOT / "board/early-logo/satooshi-bootlogo.c"
            harness = temp / "test.c"
            harness.write_text(f'#include "{source}"\n' + HARNESS)
            subprocess.run(["cc", "-std=gnu11", "-Werror", "-I", str(temp),
                            str(harness), "-o", str(temp / "check")],
                           check=True, capture_output=True, text=True)
            for scenario in ("success", "disabled", "missing", "failed", "partial", "late"):
                with self.subTest(scenario=scenario):
                    subprocess.run([str(temp / "check"), scenario], check=True,
                                   capture_output=True, text=True)


STUBS = r"""
#ifndef SATOOSHI_TEST_KERNEL
#define SATOOSHI_TEST_KERNEL
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include <sys/types.h>
#define __init
#define __initdata
#define __initconst
#define __setup(name, fn)
#define late_initcall_sync(fn)
#define device_initcall_sync(fn)
#define pr_info(...) do {} while (0)
#define pr_warn(...) do {} while (0)
#define EIO 5
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint64_t u64;
struct i2c_adapter { int unused; };
struct i2c_msg { u16 addr, flags, len; u8 *buf; };
struct kobject { int unused; };
struct attribute { const char *name; };
struct kobj_attribute {
  struct attribute attr;
  ssize_t (*show)(struct kobject *, struct kobj_attribute *, char *);
};
#define __ATTR_RO(name) { .attr = { #name }, .show = name##_show }
static struct kobject object;
static struct kobject *kernel_kobj = &object;
static struct i2c_adapter bus;
static int mode, writes, released, published, seen_on;
static struct i2c_adapter *i2c_get_adapter(int id) {
  return id == 1 && mode != 2 ? &bus : NULL;
}
static void i2c_put_adapter(struct i2c_adapter *adapter) { released++; }
static int i2c_transfer(struct i2c_adapter *adapter, struct i2c_msg *msg, int n) {
  writes++;
  if (mode == 3) return -5;
  if (mode == 4 && writes == 4) return 0;
  if (n != 1 || msg->addr != 0x3c || msg->flags != 0) return -5;
  if (writes == 1 && (msg->buf[0] != 0 || msg->buf[1] != 0xae)) return -5;
  if (msg->len == 2 && msg->buf[1] == 0xaf) seen_on++;
  return 1;
}
static u64 ktime_get_boottime_ns(void) { return 1234000000ULL; }
static u64 div_u64(u64 n, uint32_t d) { return n / d; }
static int sysfs_emit(char *buf, const char *format, ...) {
  va_list args;
  va_start(args, format);
  int result = vsnprintf(buf, 64, format, args);
  va_end(args);
  return result;
}
static int sysfs_create_file(struct kobject *kobj, struct attribute *attr) {
  published++;
  return 0;
}
#endif
"""

HARNESS = r"""
int main(int argc, char **argv) {
  if (argc != 2) return 90;
  if (!strcmp(argv[1], "disabled")) {
    mode = 1;
    if (!logo_setting("0")) return 91;
  }
  if (!strcmp(argv[1], "missing")) mode = 2;
  if (!strcmp(argv[1], "late")) mode = 2;
  if (!strcmp(argv[1], "failed")) mode = 3;
  if (!strcmp(argv[1], "partial")) mode = 4;
  if (satooshi_early_logo_init() != 0) return 92;
  if (!strcmp(argv[1], "late")) mode = 0;
  if (satooshi_early_logo_late_init() != 0) return 99;
  if (!mode) {
    char text[64];
    if (writes != 34 || released != 1 || published != 1 || seen_on != 1) return 93;
    satooshi_logo_ms_show(&object, &logo_attribute, text);
    if (strcmp(text, "1234\n")) return 94;
  } else {
    if (published || seen_on) return 95;
    if ((mode == 1 || mode == 2) && (writes || released)) return 96;
    if (mode == 3 && (writes != 1 || released != 1)) return 97;
    if (mode == 4 && (writes != 4 || released != 1)) return 98;
  }
  return 0;
}
"""

if __name__ == "__main__":
    unittest.main()
