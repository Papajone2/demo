"""Single-threaded physical device runtime; secret screens are never logged."""
import argparse
import json
import os
import sys
import time

from .controller import Controller
from .hardware import Bonnet
from .protocol import MAX_FRAME, Protocol
from .vault import Vault


def run():
    import serial
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="/dev/ttyGS0")
    parser.add_argument("--data", default="/var/lib/satooshi")
    args = parser.parse_args()
    os.umask(0o077)
    hardware = Bonnet()
    hardware.render(("SATOOSHI PRO", ["Starting USB...", "Use USB data socket", "not PWR IN"], "DIY prototype"))
    port = serial.Serial(args.port, baudrate=115200, timeout=0, write_timeout=2)
    outputs = []

    def emit(event):
        # No logging of event data or screens. Responses are sanitized by the controller.
        outputs.append((json.dumps(event, separators=(",", ":")) + "\n").encode())

    controller = Controller(Vault(args.data), emit)
    protocol = Protocol(controller)
    buffer, dropping = bytearray(), False
    try:
        while True:
            # pyserial's .dtr is a locally cached OUTPUT, not proof of host presence.
            # Heartbeat expiry in controller.tick() is the authoritative USB timeout.
            chunk = port.read(4096)
            for byte in chunk:
                if byte == 10:
                    if not dropping and buffer:
                        response = protocol.handle(bytes(buffer))
                        outputs.append((json.dumps(response) + "\n").encode())
                    elif dropping:
                        outputs.append(b'{"v":1,"id":null,"ok":false,"error":"Frame too large"}\n')
                    buffer.clear()
                    dropping = False
                elif not dropping:
                    if len(buffer) >= MAX_FRAME:
                        buffer.clear()
                        dropping = True
                    else:
                        buffer.append(byte)
            key = hardware.poll()
            if key:
                try:
                    controller.button(key)
                except Exception:
                    controller.lock()
                    controller.error = "Action failed safely"
                    controller.changed()
                    print("Device action failed; wallet locked. No signing retry.", file=sys.stderr)
            controller.tick()
            screen = controller.display()
            if controller.error:
                screen = (screen[0], [controller.error] + screen[1][:3], screen[2])
            hardware.render(screen)
            if outputs:
                try:
                    while outputs:
                        port.write(outputs[0])
                        outputs.pop(0)
                except (serial.SerialTimeoutException, serial.SerialException):
                    outputs.clear()
                    controller.lock()
            time.sleep(0.01)
    finally:
        controller.lock()
        hardware.close()
        port.close()


if __name__ == "__main__":
    run()
