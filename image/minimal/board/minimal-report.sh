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
  if test -f /run/wallet.log &&
     grep -Fq 'bwrap: loopback: Failed RTM_NEWADDR' /run/wallet.log; then
    echo "Wallet isolation failed: local loopback setup unavailable."
  fi
  test -f /run/storage-ready && echo "Encrypted-wallet data filesystem mounted."
} >/run/boot-report/satooshi-boot-status.txt
{
  echo "Satooshi USB status: built-in CDC ACM; no wallet secrets."
  for udc in /sys/class/udc/*; do
    test -d "$udc" || continue
    printf 'Controller: %s\n' "${udc##*/}"
    printf 'Function: '; cat "$udc/function" 2>/dev/null || true
    printf 'Host link state: '; cat "$udc/state" 2>/dev/null || true
  done
  if test -c /dev/ttyGS0; then
    echo "Device serial node exists."
  else
    echo "Device serial node missing."
  fi
  test ! -f /run/usb.log || cat /run/usb.log
  # Restrict output to controller/USB errors, never application payloads.
  dmesg | grep -Ei 'dwc2|dwc_otg|g_serial|gadget serial|ttyGS|udc' || true
} >/run/boot-report/satooshi-usb-status.txt
sync
