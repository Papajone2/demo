"""Check actual packaged boot inputs, not just source templates."""
from pathlib import Path
import sys


def verify(images):
    images = Path(images)
    firmware = images / "rpi-firmware"
    config = set((firmware / "config.txt").read_text().splitlines())
    for line in ("kernel=zImage", "device_tree=bcm2708-rpi-zero-w.dtb",
                 "dtoverlay=dwc2,dr_mode=peripheral", "boot_delay=0"):
        if line not in config:
            raise SystemExit(f"Packaged boot config missing: {line}")
    cmdline = (firmware / "cmdline.txt").read_text().split()
    for setting in ("g_serial.use_acm=1", "g_serial.n_ports=1",
                    "g_serial.idVendor=0x1d6b", "g_serial.idProduct=0x0104"):
        if setting not in cmdline:
            raise SystemExit(f"Packaged USB serial identity missing: {setting}")
    for relative in ("rpi-firmware/bootcode.bin", "rpi-firmware/start_cd.elf",
                     "rpi-firmware/fixup_cd.dat", "rpi-firmware/overlays/dwc2.dtbo",
                     "bcm2708-rpi-zero-w.dtb", "zImage"):
        path = images / relative
        if not path.is_file() or not path.stat().st_size:
            raise SystemExit(f"Missing boot input: {relative}")
    print("Pi Zero boot files, peripheral overlay and Chrome USB identity verified.")


if __name__ == "__main__":
    verify(sys.argv[1])
