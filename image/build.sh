#!/bin/bash
# Run ONLY on a disposable privileged Ubuntu build runner, never on the wallet.
set -Eeuo pipefail
[[ "${EUID}" -eq 0 ]] || { echo 'Run with sudo on an Ubuntu build runner.' >&2; exit 1; }
SOURCE="$(cd "$(dirname "$0")/.." && pwd)"
COMMIT="$(git -C "$SOURCE" rev-parse HEAD)"
IMAGE_NAME="satooshi-pro-0.3.0-build-${GITHUB_RUN_NUMBER:-local}-${COMMIT:0:8}.img"
BUILD="$SOURCE/build"
ROOT="$BUILD/root"
IMAGE="$BUILD/satooshi-pro-zero-w.img"
BASE_NAME=2025-05-13-raspios-bookworm-armhf-lite.img.xz
BASE_URL="https://downloads.raspberrypi.com/raspios_lite_armhf/images/raspios_lite_armhf-2025-05-13/$BASE_NAME"
BASE_SHA=a73d68b618c3ca40190c1aa04005a4dafcf32bc861c36c0d1fc6ddc48a370b6e
LOOP=""
cleanup() {
  set +e
  for point in "$ROOT/dev/pts" "$ROOT/proc" "$ROOT/sys" "$ROOT/dev" "$ROOT/boot/firmware" "$ROOT"; do
    mountpoint -q "$point" && umount "$point"
  done
  [[ -n "$LOOP" ]] && losetup -d "$LOOP"
}
trap cleanup EXIT
mkdir -p "$BUILD" "$ROOT" "$SOURCE/dist"
[[ ! -e "$IMAGE" ]] || { echo 'Use a fresh build directory.' >&2; exit 1; }
curl --fail --location --retry 3 --connect-timeout 30 "$BASE_URL" -o "$BUILD/$BASE_NAME"
echo "$BASE_SHA  $BUILD/$BASE_NAME" | sha256sum -c -
xz -dc "$BUILD/$BASE_NAME" > "$IMAGE"
truncate -s 4G "$IMAGE"
LOOP="$(losetup --find --show --partscan "$IMAGE")"
parted -s "$LOOP" resizepart 2 100%
partprobe "$LOOP"
udevadm settle
e2fsck -pf "${LOOP}p2" || [[ "$?" -eq 1 ]]
resize2fs "${LOOP}p2"
mount "${LOOP}p2" "$ROOT"
mkdir -p "$ROOT/boot/firmware"
mount "${LOOP}p1" "$ROOT/boot/firmware"

# Raspbian armhf is ARMv6-compatible; Debian/Ubuntu generic armhf is NOT.
grep -q 'Raspbian' "$ROOT/etc/os-release"
[[ -e "$ROOT/boot/firmware/bcm2708-rpi-zero-w.dtb" ]]

mount --bind /dev "$ROOT/dev"
mount --bind /dev/pts "$ROOT/dev/pts"
mount -t proc proc "$ROOT/proc"
mount -t sysfs sysfs "$ROOT/sys"
cp /usr/bin/qemu-arm-static "$ROOT/usr/bin/"
rm -f "$ROOT/etc/resolv.conf"
cp -L /etc/resolv.conf "$ROOT/etc/resolv.conf"
cat > "$ROOT/usr/sbin/policy-rc.d" <<'POLICY'
#!/bin/sh
exit 101
POLICY
chmod 755 "$ROOT/usr/sbin/policy-rc.d"
mkdir -p "$ROOT/opt/satooshi/device" "$ROOT/opt/satooshi/image"
mkdir -p "$ROOT/opt/satooshi/lib"
cp "$SOURCE/native-sr25519/target/arm-unknown-linux-gnueabihf/release/libsatooshi_sr25519.so" "$ROOT/opt/satooshi/lib/"
cp -a "$SOURCE/device/satooshi" "$ROOT/opt/satooshi/device/"
printf 'VERSION = "0.3.0"\nBUILD_COMMIT = "%s"\n' "$COMMIT" \
  > "$ROOT/opt/satooshi/device/satooshi/build_info.py"
find "$ROOT/opt/satooshi" -type d -name __pycache__ -prune -exec rm -rf {} +
cp "$SOURCE/image/"{usb-gadget.sh,satooshi.service,satooshi-usb.service,satooshi-splash.service} "$ROOT/opt/satooshi/image/"
cp "$SOURCE/requirements-core.txt" "$ROOT/opt/satooshi/"
chmod 755 "$ROOT/opt/satooshi/image/usb-gadget.sh"

# Keep the provisioning program out of stdin. Package-manager hooks can read
# stdin and otherwise consume the remaining setup commands without executing them.
cat > "$ROOT/tmp/satooshi-provision.sh" <<'CHROOT'
export DEBIAN_FRONTEND=noninteractive
# DEBIAN_FRONTEND does not answer dpkg's conffile questions. Preserve the Pi
# image's existing boot configuration explicitly, without reading any stdin.
APT_OPTIONS=(-o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold)
apt-get update
apt-get "${APT_OPTIONS[@]}" -y upgrade
apt-get "${APT_OPTIONS[@]}" install --no-install-recommends -y python3 python3-pip python3-cryptography \
  python3-pycryptodome python3-pil python3-smbus python3-rpi.gpio python3-serial i2c-tools fonts-dejavu-core
python3 -m pip install --no-deps --no-compile --target /opt/satooshi/vendor \
  -r /opt/satooshi/requirements-core.txt
getent group gpio >/dev/null || groupadd --system gpio
getent group i2c >/dev/null || groupadd --system i2c
id satooshi >/dev/null 2>&1 || useradd --system --home-dir /var/lib/satooshi \
  --shell /usr/sbin/nologin --groups gpio,i2c,dialout satooshi
install -d -o satooshi -g satooshi -m 700 /var/lib/satooshi
cp /opt/satooshi/image/satooshi*.service /etc/systemd/system/
systemctl enable satooshi-splash.service satooshi-usb.service satooshi.service
systemctl disable ssh.service ssh.socket avahi-daemon.service bluetooth.service \
  serial-getty@ttyGS0.service getty@tty1.service 2>/dev/null || true
passwd -l root
if id pi >/dev/null 2>&1; then passwd -l pi; fi
apt-get clean
rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
CHROOT
chroot "$ROOT" /usr/bin/qemu-arm-static /bin/bash -eux /tmp/satooshi-provision.sh </dev/null

# Fail before packaging if provisioning did not install the boot services/user.
chroot "$ROOT" /usr/bin/qemu-arm-static /usr/bin/id satooshi
chroot "$ROOT" /usr/bin/qemu-arm-static /bin/systemctl is-enabled \
  satooshi-splash.service satooshi-usb.service satooshi.service
chroot "$ROOT" /usr/bin/qemu-arm-static /usr/bin/systemd-analyze verify \
  /etc/systemd/system/satooshi-splash.service \
  /etc/systemd/system/satooshi-usb.service /etc/systemd/system/satooshi.service
[[ -f "$ROOT/opt/satooshi/vendor/ecdsa/__init__.py" ]]

cat >> "$ROOT/boot/firmware/config.txt" <<'CONFIG'

# Satooshi Pro / original Raspberry Pi Zero W or WH (ARMv6)
[all]
dtparam=i2c_arm=on
dtoverlay=dwc2,dr_mode=peripheral
enable_uart=0
dtoverlay=disable-wifi
dtoverlay=disable-bt
boot_delay=0
disable_splash=1
CONFIG
printf 'dwc2\nlibcomposite\ni2c-dev\n' > "$ROOT/etc/modules-load.d/satooshi.conf"
# No user setup wizard, SSH, radio networking or host-facing serial console.
sed -i -E 's/(^| )console=serial0,[0-9]+//g; s/(^| )console=ttyAMA0,[0-9]+//g' "$ROOT/boot/firmware/cmdline.txt"
mkdir -p "$ROOT/etc/modprobe.d"
printf 'blacklist brcmfmac\nblacklist bluetooth\nblacklist btbcm\nblacklist hci_uart\n' > "$ROOT/etc/modprobe.d/satooshi-offline.conf"
chroot "$ROOT" /usr/bin/qemu-arm-static /bin/systemctl mask userconfig.service userconfig-pi.service \
  ssh.service ssh.socket NetworkManager.service NetworkManager-wait-online.service \
  systemd-networkd-wait-online.service wpa_supplicant.service bluetooth.service \
  ModemManager.service hciuart.service avahi-daemon.service
chroot "$ROOT" /usr/bin/qemu-arm-static /bin/systemctl mask \
  dphys-swapfile.service triggerhappy.service keyboard-setup.service console-setup.service \
  systemd-rfkill.service systemd-rfkill.socket
# Keep OS, entropy, udev and filesystem safety services; remove only unused
# background maintenance from this offline appliance's critical boot workload.
chroot "$ROOT" /usr/bin/qemu-arm-static /bin/systemctl disable \
  apt-daily.timer apt-daily-upgrade.timer man-db.timer 2>/dev/null || true
printf 'KERNEL=="ttyGS0", GROUP="dialout", MODE="0660"\n' \
  > "$ROOT/etc/udev/rules.d/99-satooshi-serial.rules"
rm -f "$ROOT/boot/firmware/ssh" "$ROOT/boot/firmware/ssh.txt" \
  "$ROOT/boot/firmware/userconf" "$ROOT/boot/firmware/userconf.txt"
rm -f "$ROOT/etc/ssh/"ssh_host_* "$ROOT/usr/sbin/policy-rc.d"
: > "$ROOT/etc/machine-id"
rm -f "$ROOT/var/lib/dbus/machine-id" "$ROOT/var/lib/systemd/random-seed"
find "$ROOT/var/log" -type f -exec truncate -s 0 {} \;

# Execute the real ARM interpreter and crypto code under QEMU before packaging.
chroot "$ROOT" /usr/bin/qemu-arm-static /usr/bin/env \
  PYTHONPATH=/opt/satooshi/vendor:/opt/satooshi/device PYTHONDONTWRITEBYTECODE=1 \
  /usr/bin/python3 -c 'from satooshi.evm import address; from satooshi.vault import Vault; assert address(bytes(32)) == "0xF278cF59F82eDcf871d630F28EcC8056f25C1cdb"'
chroot "$ROOT" /usr/bin/qemu-arm-static /usr/bin/env \
  PYTHONPATH=/opt/satooshi/vendor:/opt/satooshi/device PYTHONDONTWRITEBYTECODE=1 \
  /usr/bin/python3 -c 'from satooshi.signing import public_keys, sign; p = public_keys(bytes(32)); assert len(p["polkadot"]) == 64; assert len(sign(bytes(32), "polkadot", b"image-preflight")["signature"]) == 128'
chroot "$ROOT" /usr/bin/qemu-arm-static /usr/bin/env \
  PYTHONPATH=/opt/satooshi/vendor:/opt/satooshi/device PYTHONDONTWRITEBYTECODE=1 \
  /usr/bin/python3 -c 'from satooshi.screen import Screen; from satooshi.controller import Controller; assert Screen().render(("SATOOSHI START", [], ""), phase="home").size == (128,64)'
# Validate what is INSTALLED inside the image, not just the checkout or manifest.
chroot "$ROOT" /usr/bin/qemu-arm-static /usr/bin/env \
  PYTHONPATH=/opt/satooshi/vendor:/opt/satooshi/device EXPECTED_COMMIT="$COMMIT" \
  PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -c '
import os
import satooshi.controller as module
from satooshi.controller import Controller
from satooshi.vault import Vault
from satooshi.build_info import BUILD_COMMIT
assert module.__file__.startswith("/opt/satooshi/device/")
status = Controller(Vault("/var/lib/satooshi"), lambda event: None).status()
assert status["version"] == "0.3.0"
assert status["buildCommit"] == os.environ["EXPECTED_COMMIT"] == BUILD_COMMIT
assert status["previewCapabilities"] == ["send", "swap", "receive", "message"]
print("Installed image firmware verified:", status["version"], BUILD_COMMIT)
'
# Compile under the target interpreter, not the runner's Python version.
chroot "$ROOT" /usr/bin/qemu-arm-static /usr/bin/python3 -m compileall \
  -q /opt/satooshi/device /opt/satooshi/vendor
# This test vector is public, never saved as a wallet.
[[ -z "$(find "$ROOT/var/lib/satooshi" -mindepth 1 -print -quit)" ]]
printf '{"product":"Satooshi Pro","firmware":"0.3.0","prototype":true,"target":"Pi Zero W/WH ARMv6","commit":"%s","base_sha256":"%s","image":"%s.xz"}\n' \
  "$COMMIT" "$BASE_SHA" "$IMAGE_NAME" > "$SOURCE/dist/build-manifest.json"
cp "$SOURCE/dist/build-manifest.json" "$ROOT/opt/satooshi/"
cp "$SOURCE/dist/build-manifest.json" "$ROOT/boot/firmware/satooshi-build.json"
sync
cleanup
LOOP=""
trap - EXIT
xz -T2 -3 "$IMAGE"
mv "$IMAGE.xz" "$SOURCE/dist/$IMAGE_NAME.xz"
(cd "$SOURCE/dist"; sha256sum *.img.xz > SHA256SUMS)
echo "Built dist/$IMAGE_NAME.xz. Physical boot timing is still required."
