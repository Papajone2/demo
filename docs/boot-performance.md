# Zero W boot optimization

The logo, USB enumeration and signing readiness are different milestones.
No physical boot-time claim is made by this source update.

## Changes

- Build the 1024-byte SSD1306 logo from the actual firmware renderer at image
  packaging time. The first-logo process does not import Pillow, fonts, PNG
  decoders, GPIO, vaults or crypto.
- The logo waits only for its own filesystem and module loading, not every
  local filesystem. It stays visible when the splash process exits.
- Initialize the wallet while USB provisioning runs, then wait boundedly for
  the local serial node. No host connection or unlock is needed to finish boot.
- Disable unused cloud-init units, alongside the existing disabled radios,
  network waits, console setup and background maintenance.
- Disable CSI/DSI automatic probing; the I2C OLED is explicitly configured.
- Bypass initramfs only when the exact installed ARMv6 kernel configuration
  proves the SD, ext4 and devtmpfs dependencies are built in, the root is the
  fixed SD/ext4 layout and no alternate kernel/include obscures selection.
  Otherwise retain initramfs. The image build prints its decision.

Root filesystem checks, entropy initialization, durable vault writes, physical
approval, security isolation and CPU thermal limits are preserved. There is
no overclock or forced-turbo configuration. This is not a custom minimal kernel
or a Buildroot replacement.

## Measure the next physical boot

In a local diagnostic shell (not exposed through the USB wallet protocol):

```sh
journalctl -b -o short-monotonic -u satooshi-splash -u satooshi \
  | grep SATOOSHI_BOOT
systemd-analyze critical-chain satooshi.service
systemd-analyze critical-chain satooshi-splash.service
systemd-analyze blame
```

Markers contain fixed stage names and kernel-relative elapsed seconds only.
They never contain recovery material, addresses, PINs or transaction contents.
The website's existing `bootReadySeconds` status remains available over USB.
Kernel-relative measurements exclude the firmware's pre-kernel time; use an
external stopwatch/video from power application for the complete duration.

Measure three normal second boots with the same card/power supply; compare
power-to-logo, Chrome detection and wallet-ready separately. First boot may
perform one-time OS work. Do not treat another person's timings as this device's.

## Research

- Raspberry Pi, *Optimising boot time on Raspberry Pi Single Board Computers*
  (2026): https://pip-assets.raspberrypi.com/categories/685-app-notes-guides-whitepapers/documents/RP-010196-WP-1-Optimising%20boot%20time%20on%20Raspberry%20Pi%20single-board%20computers.pdf
- systemd, profiling and optimization: https://systemd.io/OPTIMIZATIONS/
- Original Zero W case study (different image/network workload, not our
  benchmark): https://hallard.me/speed-up-boot-time-on-pi-zero-with-raspbian-trixie

The official guide primarily targets Pi 4/5. Their EEPROM, PCIe and power
delivery settings do not apply to this original Zero W.
