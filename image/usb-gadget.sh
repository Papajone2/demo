#!/bin/bash
set -euo pipefail
G=/sys/kernel/config/usb_gadget/satooshi
STAGE=starting
report() {
  local result=$?
  # Only fixed startup state: never entropy, PINs, addresses, messages or keys.
  if mountpoint -q /boot/firmware; then
    if ! {
      printf 'Satooshi Pro USB startup\nstage=%s\nexit_code=%s\n' "$STAGE" "$result"
      if [[ -r "$G/UDC" ]]; then printf 'bound_controller=%s\n' "$(cat "$G/UDC")"; fi
      if [[ -c /dev/ttyGS0 ]]; then echo 'serial_node=present'; else echo 'serial_node=absent'; fi
      echo 'This report does not establish that a computer detected the device.'
    } > /boot/firmware/satooshi-usb-status.txt; then
      echo 'Could not write the non-secret USB startup report.' >&2
    fi
  fi
}
trap report EXIT
STAGE=load_controller
modprobe dwc2
modprobe libcomposite
mountpoint -q /sys/kernel/config || mount -t configfs none /sys/kernel/config
STAGE=configure_gadget
# Configfs attributes can have a nonzero stat size while reading as empty.
# Inspect the actual binding, not `test -s`, and allow partial setup to recover.
if [[ ! -d "$G" || -z "$(cat "$G/UDC")" ]]; then
  mkdir -p "$G"
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
  [[ -L "$G/configs/c.1/acm.usb0" ]] || ln -s "$G/functions/acm.usb0" "$G/configs/c.1/acm.usb0"
fi
STAGE=wait_for_controller
for attempt in $(seq 1 200); do
  UDC="$(find /sys/class/udc -mindepth 1 -maxdepth 1 -printf '%f\n' | head -n1)"
  if [[ -n "$UDC" ]]; then
    STAGE=bind_controller
    [[ -n "$(cat "$G/UDC")" ]] || echo "$UDC" > "$G/UDC"
    STAGE=wait_for_serial_node
    # ttyGS0 is created asynchronously.
    for wait in $(seq 1 100); do
      if [[ -c /dev/ttyGS0 ]]; then
        chown root:dialout /dev/ttyGS0
        chmod 660 /dev/ttyGS0
        STAGE=serial_ready
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
