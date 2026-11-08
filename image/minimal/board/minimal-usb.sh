#!/bin/sh
set -eu
mount -t configfs configfs /sys/kernel/config
g=/sys/kernel/config/usb_gadget/satooshi
mkdir -p "$g"
echo 0x1d6b >"$g/idVendor"
echo 0x0104 >"$g/idProduct"
echo 0x0200 >"$g/bcdUSB"
echo 0x0300 >"$g/bcdDevice"
mkdir -p "$g/strings/0x409" "$g/configs/c.1/strings/0x409" "$g/functions/acm.usb0"
id="$(tr -d '\000\n' </proc/device-tree/serial-number)"
test -n "$id"
printf '%s' "$id" >"$g/strings/0x409/serialnumber"
echo Satooshi >"$g/strings/0x409/manufacturer"
echo Satooshi >"$g/strings/0x409/product"
echo 'Satooshi serial' >"$g/configs/c.1/strings/0x409/configuration"
echo 250 >"$g/configs/c.1/MaxPower"
ln -s "$g/functions/acm.usb0" "$g/configs/c.1/acm.usb0"
tries=0
while :; do
  udc="$(ls /sys/class/udc | head -n 1)"
  if test -n "$udc"; then echo "$udc" >"$g/UDC"; break; fi
  tries=$((tries + 1)); test "$tries" -lt 100; sleep 0.05
done
printf 'SATOOSHI_BOOT stage=usb_bound kernel_seconds='
cut -d ' ' -f 1 /proc/uptime
