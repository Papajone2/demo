#!/bin/sh
set -eu
# USB CDC ACM now binds inside the kernel, before root mount, PIN or Python.
# This script observes it; it must never create a competing configfs gadget.
sys="${SATOOSHI_USB_SYS_ROOT:-/sys}"
dev="${SATOOSHI_USB_DEV_ROOT:-/dev}"
proc="${SATOOSHI_USB_PROC_ROOT:-/proc}"
tries=0
while :; do
  for udc in "$sys"/class/udc/*; do
    if test -d "$udc" && test -c "$dev/ttyGS0"; then
      printf 'SATOOSHI_BOOT stage=usb_bound kernel_seconds='
      cut -d ' ' -f 1 "$proc/uptime"
      printf 'Controller: %s\n' "${udc##*/}"
      printf 'Function: '; cat "$udc/function" 2>/dev/null || true
      printf 'Host link state: '; cat "$udc/state" 2>/dev/null || true
      exit 0
    fi
  done
  tries=$((tries + 1))
  if test "$tries" -ge "${SATOOSHI_USB_MAX_TRIES:-200}"; then
    echo "USB serial unavailable: built-in CDC ACM did not create its device node."
    ls "$sys/class/udc" 2>/dev/null || true
    exit 1
  fi
  sleep 0.05
done
