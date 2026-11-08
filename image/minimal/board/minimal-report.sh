#!/bin/sh
set -eu
mkdir -p /run/boot-report
mount -t vfat -o nosuid,nodev,noexec /dev/mmcblk0p1 /run/boot-report
trap 'umount /run/boot-report' EXIT
{
  echo "Satooshi minimal OS: times since Linux started, not power-on."
  uname -r
  logo_ms="$(cat /sys/kernel/satooshi_logo_ms 2>/dev/null || true)"
  case "$logo_ms" in
    ''|*[!0-9]*) ;;
    *) echo "Initial logo: $logo_ms milliseconds after Linux started." ;;
  esac
  for log in /run/splash.log /run/usb.log /run/wallet.log; do
    test ! -f "$log" || grep -E 'SATOOSHI_BOOT stage=[a-z_]+( kernel_seconds=[0-9]+\.[0-9]+)?$' "$log" || true
  done
  test ! -f /run/wallet-startup-error || echo "Required device nodes unavailable."
  test -f /run/storage-ready && echo "Encrypted-wallet data filesystem mounted."
} >/run/boot-report/satooshi-boot-status.txt
sync
