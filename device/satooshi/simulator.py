"""Local terminal simulator. Secrets are shown only in its local display.

Linux/macOS PTY can be opened by a serial test client. Web Serial cannot choose
a PTY on most browsers; use a real USB device for the final browser flow.
"""
import argparse
import json
import os
import pty
import select
import sys
import termios
import tty
from pathlib import Path

from .controller import Controller
from .protocol import Protocol, MAX_FRAME
from .vault import Vault


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="simulator-data")
    args = parser.parse_args()
    if not sys.stdin.isatty():
        raise SystemExit("Run simulator interactively in a terminal (TTY required).")
    master, slave = pty.openpty()
    tty.setraw(slave)
    path = os.ttyname(slave)
    controller = Controller(Vault(Path(args.data)), lambda e: os.write(master, (json.dumps(e) + "\n").encode()))
    protocol = Protocol(controller)
    settings = termios.tcgetattr(sys.stdin)
    tty.setcbreak(sys.stdin.fileno())
    buffer, last = b"", None
    print("SIMULATOR / not hardware protection. Serial PTY: " + path)
    print("Keyboard: a = A, b = B, Enter = both, q = quit.")
    try:
        while True:
            readable, _, _ = select.select([master, sys.stdin], [], [], 0.05)
            if sys.stdin in readable:
                char = sys.stdin.read(1)
                if char == "q":
                    break
                key = {"a": "a", "b": "b", "\n": "both"}.get(char)
                if key:
                    controller.button(key)
            if master in readable:
                buffer += os.read(master, 4096)
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    os.write(master, (json.dumps(protocol.handle(line)) + "\n").encode())
                if len(buffer) > MAX_FRAME:
                    buffer = b""
            controller.tick()
            screen = controller.display()
            if screen != last:
                print("\n[" + screen[0] + "]\n" + "\n".join(screen[1]) + "\n" + screen[2])
                last = screen
    finally:
        controller.lock()
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, settings)
        os.close(master)
        os.close(slave)


if __name__ == "__main__":
    run()
