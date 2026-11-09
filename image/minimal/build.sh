#!/bin/bash
# Explicit manual build only, on a disposable privileged Ubuntu runner.
set -euo pipefail
external="$(cd "$(dirname "$0")" && pwd)"
source_dir="$(cd "$external/../.." && pwd)"
work="$source_dir/build-minimal"
dist="$source_dir/dist-minimal"
source "$external/buildroot.lock"
export SATOOSHI_LOGO_PYTHON="$(command -v python3)"
"$SATOOSHI_LOGO_PYTHON" -c 'from PIL import Image' # Fail before an expensive cross-build.
command -v cargo >/dev/null
test -x /usr/bin/qemu-arm-static
for command in qemu-system-arm fdtput debugfs; do
  command -v "$command" >/dev/null
done
sudo -n true
# Buildroot executes these hooks directly; missing Git execute bits otherwise
# fail only after the entire toolchain, kernel and userspace have compiled.
for entry in board/post-build.sh board/post-image.sh \
  board/overlay/etc/init.d/rcS board/overlay/etc/init.d/rcK \
  board/overlay/usr/sbin/satooshi-run; do
  test -x "$external/$entry" || {
    echo "Required script is not executable: $entry" >&2
    exit 1
  }
done
mkdir -p "$work" "$dist"
archive="$work/buildroot.tar.gz"
if ! test -f "$archive"; then
  curl -fL --retry 3 "https://codeload.github.com/buildroot/buildroot/tar.gz/$BUILDROOT_COMMIT" -o "$archive"
fi
echo "$BUILDROOT_SHA256  $archive" | sha256sum -c -
if ! test -d "$work/buildroot-$BUILDROOT_COMMIT"; then
  tar -xzf "$archive" -C "$work"
fi
cargo vendor --locked --manifest-path "$source_dir/native-sr25519/Cargo.toml" "$work/cargo-vendor" >/dev/null
"$SATOOSHI_LOGO_PYTHON" "$external/check-rust.py" "$work/cargo-vendor"
export SATOOSHI_SOURCE_COMMIT="$(git -C "$source_dir" rev-parse HEAD)"
export SATOOSHI_BUILD_ID="${GITHUB_RUN_NUMBER:-local}-${SATOOSHI_SOURCE_COMMIT:0:8}"
export SATOOSHI_DIST="$dist"
export SATOOSHI_FIRMWARE_DIR="$source_dir"
export SATOOSHI_CARGO_VENDOR="$work/cargo-vendor"
bash "$external/configure.sh" "$work/buildroot-$BUILDROOT_COMMIT" "$work/output"
make -C "$work/buildroot-$BUILDROOT_COMMIT" BR2_LOCALVERSION= O="$work/output" \
  BR2_EXTERNAL="$external" -j"$(nproc)"
