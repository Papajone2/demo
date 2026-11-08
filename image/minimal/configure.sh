#!/bin/bash
# Configuration only: this does not compile a kernel or make an SD image.
set -euo pipefail
external="$(cd "$(dirname "$0")" && pwd)"
source_dir="$(realpath "${1:?Pass the pinned Buildroot source directory}")"
output="$(realpath -m "${2:?Pass a separate output directory}")"
# An extracted upstream archive must not inspect or refresh the parent app's Git index.
export GIT_CEILING_DIRECTORIES="$(dirname "$source_dir")"
export GIT_OPTIONAL_LOCKS=0
# Upstream setlocalversion refreshes a Git index even in a source archive.
# Never let it discover the surrounding firmware/app repository.
if ! test -e "$source_dir/.git"; then
  install -m 755 "$external/archive-version.sh" "$source_dir/support/scripts/setlocalversion"
fi
mkdir -p "$output"
make -C "$source_dir" BR2_LOCALVERSION= O="$output" BR2_EXTERNAL="$external" raspberrypi0w_defconfig
cat "$external/configs/satooshi.fragment" >>"$output/.config"
make -C "$source_dir" BR2_LOCALVERSION= O="$output" BR2_EXTERNAL="$external" olddefconfig
python3 "$external/check-config.py" "$output/.config"
