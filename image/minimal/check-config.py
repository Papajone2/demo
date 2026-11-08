"""Fail closed if Kconfig silently drops a required package or isolation flag."""
from pathlib import Path
import sys


def settings(text):
    result = {}
    for line in text.splitlines():
        if line.startswith("# BR2_") and line.endswith(" is not set"):
            result[line[2:-11]] = "n"
        elif line.startswith("BR2_") and "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
    return result


def check(path):
    actual = settings(Path(path).read_text())
    expected = settings((Path(__file__).parent / "configs/satooshi.fragment").read_text())
    expected.update(BR2_arm1176jzf_s="y", BR2_arm="y", BR2_TARGET_ROOTFS_EXT2_4="y")
    wrong = [f"{key}: expected {value}, got {actual.get(key, 'missing')}"
             for key, value in expected.items() if actual.get(key) != value]
    if wrong:
        raise SystemExit("Minimal-OS configuration is incomplete:\n" + "\n".join(wrong))
    print("ARMv6, runtime dependencies, read-only root and sandbox configuration verified.")


if __name__ == "__main__":
    check(sys.argv[1])
