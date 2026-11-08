#!/bin/bash
set -euo pipefail
target="${1:?}"
board="$(cd "$(dirname "$0")" && pwd)"
# Removing initramfs/modules is permitted only with all boot dependencies built in.
python3 "$board/verify-kernel.py" "$BUILD_DIR"
for binary in usr/bin/bwrap usr/bin/setpriv usr/sbin/rngd sbin/e2fsck sbin/init; do
  test -x "$target/$binary" || { echo "Required target binary missing: $binary" >&2; exit 1; }
done
chmod 755 "$target/etc/init.d/rcS" "$target/etc/init.d/rcK" "$target/usr/sbin/satooshi-run"
install -d "$target/data" "$target/opt/satooshi/image"
install -m 755 "$board/"minimal-{usb,report}.sh "$target/opt/satooshi/image/"
install -m 644 "$board/target-smoke.py" "$target/opt/satooshi/image/"
fonts="$target/usr/share/fonts/truetype/dejavu"
mkdir -p "$fonts"
for font in DejaVuSans.ttf DejaVuSansMono.ttf; do
  found="$(find "$target/usr/share/fonts" -name "$font" -not -path "$fonts/*" | head -n1)"
  test -n "$found"
  install -m 644 "$found" "$fonts/$font"
done
printf 'VERSION = "0.3.0"\nBUILD_COMMIT = "%s"\n' \
  "${SATOOSHI_SOURCE_COMMIT:?}" >"$target/opt/satooshi/device/satooshi/build_info.py"
# Precompile with Buildroot's matching Python, never the runner's Python version.
# Unchecked hashes are appropriate only because application code is read-only.
"$HOST_DIR/bin/python3" -m compileall -q --invalidation-mode unchecked-hash "$target/opt/satooshi/device"
cleanup() {
  sudo umount "$target/dev" 2>/dev/null || true
  rm -f "$target/usr/bin/qemu-arm-static"
}
trap cleanup EXIT
cp /usr/bin/qemu-arm-static "$target/usr/bin/qemu-arm-static"
sudo mount --bind /dev "$target/dev"
# ARM1176 emulation catches accidental ARMv7/NEON binaries before packaging.
sudo env QEMU_CPU=arm1176 PYTHONPATH=/opt/satooshi/device PYTHONDONTWRITEBYTECODE=1 \
  chroot "$target" /usr/bin/qemu-arm-static \
  /usr/bin/python3 /opt/satooshi/image/target-smoke.py
