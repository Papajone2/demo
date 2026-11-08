# Original Pi Zero W/WH startup

## Comparison

[PiTrezor's image](https://github.com/heneault/yocto-pitrezor) uses
`core-image-minimal`, SysV init, a read-only root and a compiled wallet.
Its configuration removes desktop/network features and several init scripts.
This is not a drop-in replacement for Satooshi's Python signing runtime,
encrypted data storage or USB protocol.

## Changes retained in this image

- Start the wallet and USB setup concurrently, not USB setup followed by wallet
  initialization. The public splash still precedes the application's display.
- Wait for the actual application/data filesystems and safe root remount,
  rather than all unrelated local mounts, including the boot FAT partition.
- Use an I2C-only headless profile: no HDMI framebuffer, VC4 graphics or audio.
  This intentionally removes HDMI-console output; the bonnet remains supported.
- Select `gpu_mem=16` only if the matching cut-down firmware files exist and no
  explicit firmware override makes that choice ambiguous.
- Keep USB startup diagnostics in RAM; collect them to the boot partition after
  about 60 seconds, outside the wallet's readiness path.

Filesystem checking, root-device waits, entropy initialization, PIN handling,
encrypted vault format and signing authorization are not weakened for speed.

After a future build/flash, read `satooshi-boot-status.txt` from the SD card's
boot partition after leaving the device powered for at least one minute.
It separates logo, serial and wallet stages. Linux timestamps exclude firmware
time before Linux starts; measure true power-to-logo with a recording.
Local USB readiness is not proof of Chrome or host enumeration.

No eight-second or faster result is claimed without physical measurements.
A purpose-built minimal OS is a separate, opt-in migration; the current image
continues to use Raspberry Pi OS.

References: [PiTrezor init recipe](https://github.com/heneault/yocto-pitrezor/blob/master/meta-pitrezor/recipes-core/images/pitrezor-image.bb),
[PiTrezor platform configuration](https://github.com/heneault/yocto-pitrezor/blob/master/build/conf/local.conf),
[Raspberry Pi legacy configuration](https://www.raspberrypi.com/documentation/computers/legacy_config_txt.html).
