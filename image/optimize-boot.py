"""Build-time, fail-safe optimization for this fixed SD/ext4 appliance."""
from pathlib import Path
import re
import sys


def optimize(root):
    root = Path(root)
    boot = root / "boot/firmware"
    config = boot / "config.txt"
    text = config.read_text()
    # Fixed I2C OLED: neither SDL, HDMI/KMS, camera nor audio is used. Do not
    # apply newer-board EEPROM/overclock advice to the original ARMv6 Zero W.
    text = re.sub(r"\n# BEGIN SATOOSHI HEADLESS\n.*?# END SATOOSHI HEADLESS\n", "\n", text, flags=re.S)
    text = re.sub(r"^([ \t]*dtoverlay=vc4-(?:kms|fkms)-v3d(?:,[^\n]*)?)$",
                  r"# Satooshi I2C-only display: \1", text, flags=re.M)
    profile = ("\n# BEGIN SATOOSHI HEADLESS\n[all]\ncamera_auto_detect=0\n"
               "display_auto_detect=0\ndtparam=audio=off\nhdmi_ignore_hotplug=1\n"
               "max_framebuffers=0\n")
    # gpu_mem=16 selects cut-down VideoCore firmware on the original Zero W.
    # Keep the stock allocation if either matching file or selection is uncertain.
    cutdown = all((boot / name).is_file() and (boot / name).stat().st_size > 0
                  for name in ("start_cd.elf", "fixup_cd.dat"))
    custom_firmware = re.search(r"^\s*(start_file|fixup_file|start_x)\s*=", text, re.M)
    if cutdown and not custom_firmware:
        profile += "gpu_mem=16\n"
    text += profile + "# END SATOOSHI HEADLESS\n"
    # Avoid painting an unused HDMI console; retain rootwait, fsck, entropy and
    # every unrelated boot argument. Kernel diagnostics remain in the journal.
    cmdline_path = boot / "cmdline.txt"
    arguments = cmdline_path.read_text().split()
    arguments = [arg for arg in arguments if arg != "console=tty1"
                 and arg != "quiet" and not re.fullmatch(r"loglevel=\d+", arg)]
    cmdline_path.write_text(" ".join(arguments + ["quiet", "loglevel=3"]) + "\n")
    # Only bypass initramfs with exact installed ARMv6 kernel evidence. Absence
    # of lsmod entries is NOT proof of built-in drivers.
    versions = sorted(p.name for p in (root / "lib/modules").glob("*") if p.name.endswith("-rpi-v6"))
    reason = "kept: exact ARMv6 kernel configuration unavailable"
    if len(versions) == 1:
        version = versions[0]
        candidates = [root / "boot" / f"config-{version}", boot / f"config-{version}"]
        kernel_config = next((p for p in candidates if p.is_file()), None)
        if kernel_config:
            flags = set(kernel_config.read_text().splitlines())
            required = {"CONFIG_MMC=y", "CONFIG_MMC_BLOCK=y", "CONFIG_EXT4_FS=y",
                        "CONFIG_DEVTMPFS=y", "CONFIG_DEVTMPFS_MOUNT=y"}
            sd_driver = bool({"CONFIG_MMC_BCM2835=y", "CONFIG_MMC_BCM2835_SDHOST=y"} & flags)
            cmdline = (boot / "cmdline.txt").read_text()
            fstab = (root / "etc/fstab").read_text()
            sd_ext4 = any(len(fields := line.split()) >= 3 and fields[1:3] == ["/", "ext4"]
                          and (fields[0].startswith("PARTUUID=") or fields[0] == "/dev/mmcblk0p2")
                          for line in fstab.splitlines() if not line.lstrip().startswith("#"))
            # A config include or explicit alternate kernel makes the selected
            # kernel uncertain: preserve boot compatibility, not speculative speed.
            ambiguous = re.search(r"^\s*(include\s|kernel\s*=|os_prefix\s*=)", text, re.M)
            if required <= flags and sd_driver and sd_ext4 and "rootfstype=ext4" in cmdline and not ambiguous:
                text = re.sub(r"^([ \t]*initramfs[ \t]+[^\n]*)$", r"# Satooshi bypass: \1", text, flags=re.M)
                text += "\n[all]\nauto_initramfs=0\n"
                reason = f"bypassed: {version} proves built-in SD/ext4/devtmpfs"
            else:
                reason = "kept: kernel/root configuration did not satisfy every safety check"
    config.write_text(text)
    print("Satooshi initramfs:", reason)
    return reason


if __name__ == "__main__":
    optimize(sys.argv[1])
