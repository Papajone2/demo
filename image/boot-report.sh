#!/bin/sh
# Delayed, public-only diagnostics; never part of wallet/USB readiness.
set -eu
umask 077
boot=/boot/firmware
mountpoint -q "$boot" || { echo "Boot partition is not mounted." >&2; exit 1; }
temp="$(mktemp "$boot/.satooshi-boot-status.XXXXXX")"
trap 'rm -f "$temp"' EXIT
{
  printf 'Satooshi boot timing report\n'
  printf 'Timings are since Linux started, not since power-on.\n'
  printf 'USB node presence does not prove host/browser enumeration.\n\n'
  printf 'Kernel: '; uname -r
  if test -r /proc/device-tree/model; then
    printf 'Model: '; tr '\000' '\n' < /proc/device-tree/model
  fi
  printf '\nBoot summary:\n'
  systemd-analyze time 2>/dev/null || true
  printf '\nPublic application stages:\n'
  journalctl -b --no-pager -o short-monotonic \
    -u satooshi-splash.service -u satooshi.service |
    grep -E 'SATOOSHI_BOOT stage=(logo_native|logo|runtime_started|imports_ready|serial_ready|wallet_ready)( kernel_seconds=[0-9]+\.[0-9]{3})?$' || true
  printf '\nService timings (microseconds since Linux boot):\n'
  systemctl show satooshi-splash.service satooshi-usb.service satooshi.service \
    -p Id -p ActiveState -p SubState -p ExecMainStartTimestampMonotonic \
    -p ExecMainExitTimestampMonotonic
  printf '\nLocal USB serial node: '
  if test -c /dev/ttyGS0; then printf 'present\n'; else printf 'absent\n'; fi
  if test -f /run/satooshi-usb-status.txt; then
    printf '\nPublic USB setup report:\n'
    cat /run/satooshi-usb-status.txt
  fi
} > "$temp"
mv "$temp" "$boot/satooshi-boot-status.txt"
if test -f /run/satooshi-usb-status.txt; then
  cp /run/satooshi-usb-status.txt "$boot/satooshi-usb-status.txt"
fi
