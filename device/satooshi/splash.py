"""Early public-only splash. No vault, crypto, GPIO, USB or signing imports."""
import time
from .oled import OLED
from .screen import Screen


def run():
    # I2C character devices can appear just after modules-load completes.
    for attempt in range(30):
        try:
            display = OLED()
            try:
                display.show(Screen().render(
                    ("SATOOSHI LOGO", [], ""), phase="home"))
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
