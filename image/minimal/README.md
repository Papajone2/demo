# Build compatibility checks

The minimal profile uses Buildroot's Rust/Cargo 1.82.0. Its native signing
lockfile retains `zeroize_derive` 1.4.2 (edition 2021); 1.5.0 requires Rust 1.85.
The preparation helper applies the exact compatibility patch idempotently.
CI compiles the native library with 1.82.0 before the expensive image build,
and the build checks every vendored manifest's minimum Rust version and edition.
When updating dependencies, keep these checks and the ARM1176 runtime test.
The runtime test invokes ARM Python directly through QEMU rather than relying
on the host's optional binfmt registration to execute an ARM `env` child.

# Satooshi minimal OS — original Pi Zero W/WH

**Status: source preparation, not a built or physically verified image.**
No measured boot-time claim is made. This profile is separate from the existing
Raspberry Pi OS build, which remains the known fallback.

## Goal and architecture

The earliest practical public logo, USB enumeration and usable wallet, measured
separately. Inspired by PiTrezor's minimal appliance architecture; no Trezor
signer, keys or branding is substituted.

- Pinned Buildroot **2025.02.19 LTS**, original ARM1176/ARMv6, hard-float glibc.
- Small BusyBox init rather than the Raspberry Pi OS/systemd dependency graph.
- SD/ext4, I2C OLED, GPIO, hardware RNG and USB serial drivers built into Linux.
  There is no initramfs or module-loading wait. Packaging rejects a kernel
  without the required built-in drivers.
- A tiny built-in I2C initializer draws the fixed public logo during Linux
  initialization, before root filesystem mounting or userspace scripts.
  It first tries immediately after built-in device drivers. If the adapter is
  still deferred, a later init stage checks once again without sleeping; failed
  transfers are not repeatedly retried in the kernel.
  It releases the adapter immediately; it does not replace the wallet/display
  driver or access any wallet data. Bitmap and drawing code are freed after
  kernel initialization.
- If early I2C is unavailable, the existing native userspace splash remains the
  fallback. A successful early frame is not redrawn by the startup shell.
  USB follows this first-logo step, before Python/storage checks. No radio networking,
  desktop, login console, package manager or first-boot expansion wizard.
- Read-only system; separate ext4 partition holds the existing encrypted-vault
  format. Startup checks that filesystem and never silently formats a failed one.
- Existing device code and protocol are reused. Python, mnemonic, embit, ECDSA,
  OpenSSL/cryptography, Cryptodome, Pillow/fonts, SMBus, serial, GPIO and the Rust
  sr25519 bridge are explicitly included; wallet support is not removed for speed.
- Privilege dropping, no-new-privileges, read-only code, private temporary
  directories and no-network namespace isolation remain enforced with bubblewrap.
  Do not replace this with a root Python process to obtain a better benchmark.
- Hardware entropy stays enabled; kernel getrandom readiness is never bypassed.
- Python application bytecode is precompiled using the matching target Python
  version. ARM1176 QEMU smoke checks must pass before an image is packaged.

## Prepare and validate without building an image

From the parent workspace:

```sh
bash scripts/prepare-minimal-firmware.sh
python3 -m unittest discover -s hardware/minimal-os/tests -p 'test_*.py' -v
```

The parent `hardware/minimal-os` tree is canonical; the ignored firmware checkout
receives it at `image/minimal`. The script adds a **manual-only** GitHub workflow
locally. It does not push GitHub changes, dispatch builds, flash cards, or modify
the existing `image/build.sh`/old build workflow.

`configure.sh <pinned-buildroot-source> <separate-output>` resolves and checks
the real ARMv6 Kconfig including every required package. This is configuration
validation, not a kernel/image build. The source archive's version helper is
replaced with the explicit archive-only helper so it cannot refresh the parent
repository's Git index or incorporate unrelated parent Git metadata.

## When an image build is explicitly requested

Publish the prepared firmware sources, then run **Build minimal Pi Zero W image**
in GitHub Actions. The first cold build includes a complete compiler/kernel/
Python/crypto stack and can take hours, unlike customizing a downloaded OS.
The workflow has a six-hour ceiling. Never claim a successful image build merely
because configuration validation passed.

The workflow runs existing host wallet regression checks, cross-compiles the
actual ARMv6 runtime and sr25519 library, tests imports/crypto/fonts under
`QEMU_CPU=arm1176`, checks MBR and root/data filesystems, then uploads uniquely
named `.img.xz`, checksum, configuration and build manifest.

## Physical validation / migration

**Use a spare SD card. Flashing erases the chosen card, including any wallet on
it. Keep the existing working card unchanged and keep the recovery backup safe.**
There is no automatic private-key migration from the old card, no new recovery
phrase scheme, and no browser seed export.

Until physical checks pass, this is an experimental alternative, not a proven
replacement. Verify:

1. Power-to-logo, host USB detection and website-ready time across repeat boots.
2. Namespace support and GPIO/serial access without root privileges.
3. PIN lock after power cycling; recovery and wallet identity match existing
   public addresses when deliberately restoring the same phrase on-device.
4. Every supported signing family with fixed unfunded vectors before real funds.
5. Hardware receive approval, send, swaps, staking and interrupted power handling.

The delayed public report remains available as `satooshi-boot-status.txt` on the
boot partition. Kernel-relative times do not include firmware startup time.
An early success also exposes the first-logo time in milliseconds at
`/sys/kernel/satooshi_logo_ms`. Add `satooshi_logo=0` to `cmdline.txt` to disable
the kernel renderer and use the native fallback without changing the wallet.
This is prepared source, not proof of a power-on-to-logo time: compilation,
I2C behavior and actual timing must still pass the new image/physical checks.

References:
- https://github.com/heneault/yocto-pitrezor/blob/master/meta-pitrezor/recipes-core/images/pitrezor-image.bb
- https://github.com/heneault/yocto-pitrezor/blob/master/build/conf/local.conf
- https://buildroot.org/downloads/manual/manual.html
- https://kernel.googlesource.com/pub/scm/linux/kernel/git/torvalds/linux/+/refs/tags/v6.12/init/main.c
