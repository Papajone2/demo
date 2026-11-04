#!/bin/bash
set -euo pipefail
modprobe libcomposite
mountpoint -q /sys/kernel/config || mount -t configfs none /sys/kernel/config
G=/sys/kernel/config/usb_gadget/satooshi
if [[ -d "$G" ]]; then
  [[ -s "$G/UDC" ]] && exit 0
else
  mkdir "$G"
  # Linux Foundation development/example IDs. NOT a production VID/PID allocation.
  echo 0x1d6b > "$G/idVendor"
  echo 0x0104 > "$G/idProduct"
  echo 0x0100 > "$G/bcdDevice"
  echo 0x0200 > "$G/bcdUSB"
  mkdir -p "$G/strings/0x409"
  SERIAL="$(tr -d '\n' < /etc/machine-id)"
  [[ -n "$SERIAL" ]] || SERIAL="$(cat /proc/sys/kernel/random/uuid)"
  printf '%s' "${SERIAL:0:16}" > "$G/strings/0x409/serialnumber"
  echo Satooshi > "$G/strings/0x409/manufacturer"
  echo 'Satooshi Pro' > "$G/strings/0x409/product"
  mkdir -p "$G/configs/c.1/strings/0x409"
  echo 'USB serial signing prototype' > "$G/configs/c.1/strings/0x409/configuration"
  echo 250 > "$G/configs/c.1/MaxPower"
  mkdir -p "$G/functions/acm.usb0"
  ln -s "$G/functions/acm.usb0" "$G/configs/c.1/acm.usb0"
fi
for attempt in $(seq 1 100); do
  UDC="$(find /sys/class/udc -mindepth 1 -maxdepth 1 -printf '%f\n' | head -n1)"
  if [[ -n "$UDC" ]]; then
    echo "$UDC" > "$G/UDC"
    # ttyGS0 is created asynchronously.
    for wait in $(seq 1 100); do
      if [[ -c /dev/ttyGS0 ]]; then
        chown root:dialout /dev/ttyGS0
        chmod 660 /dev/ttyGS0
        exit 0
      fi
      sleep 0.1
    done
    break
  fi
  sleep 0.1
done
echo 'USB gadget did not appear; use the Zero W USB DATA port.' >&2
exit 1
