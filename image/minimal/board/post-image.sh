#!/bin/bash
set -euo pipefail
images="${1:?}"
board="$(cd "$(dirname "$0")" && pwd)"
rm -rf "${BUILD_DIR:?}/genimage-satooshi"
"$HOST_DIR/bin/genimage" --rootpath "$TARGET_DIR" \
  --tmppath "$BUILD_DIR/genimage-satooshi" --inputpath "$images" \
  --outputpath "$images" --config "$board/genimage.cfg"
python3 "$board/verify-image.py" "$images/satooshi-minimal.img"
name="satooshi-minimal-0.3.0-${SATOOSHI_BUILD_ID:?}"
mkdir -p "${SATOOSHI_DIST:?}"
xz -T2 -6 -c "$images/satooshi-minimal.img" >"$SATOOSHI_DIST/$name.img.xz"
(cd "$SATOOSHI_DIST"; sha256sum "$name.img.xz" >"$name.img.xz.sha256")
cp "${BR2_CONFIG:?}" "$SATOOSHI_DIST/$name.buildroot-config"
printf 'build=%s\nsource=%s\nprofile=minimal-armv6\n' "$SATOOSHI_BUILD_ID" \
  "$SATOOSHI_SOURCE_COMMIT" >"$SATOOSHI_DIST/$name.manifest"
