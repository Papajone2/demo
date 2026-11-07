"""Early public-only splash. No vault, crypto, GPIO, USB or signing imports."""
import time
import os
from .oled import OLED
from .boot_timing import mark


def run():
    # Generated from the actual Screen renderer while building the image.
    # Boot does not need Pillow, FreeType, PNG decoding or any wallet library.
    with open(os.path.join(os.path.dirname(__file__), "assets", "splash.bin"), "rb") as source:
        frame = source.read(1025)
    if len(frame) != 1024:
        raise ValueError("Missing or invalid compiled splash")
    # I2C character devices can appear just after modules-load completes.
    for attempt in range(30):
        try:
            display = OLED()
            try:
                display.show_bytes(frame)
                mark("logo")
            finally:
                # Leave the image visible until the wallet takes over.
                display.close(blank=False)
            return
        except OSError:
            if attempt == 29:
                raise
            time.sleep(0.1)


if __name__ == "__main__":
    run()
