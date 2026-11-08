from pathlib import Path
import sys


def verify(build_dir):
    configs = list(Path(build_dir).glob("linux-*/.config"))
    if len(configs) != 1:
        raise SystemExit("Expected exactly one configured kernel; refusing ambiguous image.")
    actual = set(configs[0].read_text().splitlines())
    fragment = (Path(__file__).parent / "kernel.fragment").read_text().splitlines()
    missing = [line for line in fragment if line.endswith("=y") and line not in actual]
    if "CONFIG_MODULES=y" in actual or "CONFIG_BLK_DEV_INITRD=y" in actual:
        missing.append("Built-in-only kernel without initramfs required")
    if missing:
        raise SystemExit("Kernel cannot safely boot this appliance:\n" + "\n".join(missing))
    print("SD/ext4, I2C, GPIO, entropy, USB and namespace drivers are built in.")


def verify_logo(build_dir):
    objects = list(Path(build_dir).glob("linux-*/init/satooshi-bootlogo.o"))
    if len(objects) != 1:
        raise SystemExit("Required early-logo kernel object was not built.")
    header = objects[0].read_bytes()[:52]
    if (len(header) < 52 or header[:6] != b"\x7fELF\x01\x01"
            or int.from_bytes(header[18:20], "little") != 40):
        raise SystemExit("Early logo must be a compiled 32-bit ARM object.")
    symbol_map = objects[0].parents[1] / "System.map"
    if not symbol_map.is_file() or "satooshi_early_logo_init" not in symbol_map.read_text():
        raise SystemExit("Early-logo initializer was not linked into the kernel.")
    print("Early logo is compiled for ARM and linked into the kernel.")


if __name__ == "__main__":
    verify(sys.argv[1])
    verify_logo(sys.argv[1])
