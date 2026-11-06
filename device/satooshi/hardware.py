"""Provisional Adafruit 3531: SSD1306 128x64 I2C, A=BCM5 B=BCM6.

No joystick pins are initialized. Failure is explicit, not a simulated device.
"""
import time
from .screen import Screen
from .oled import OLED


class Bonnet:
    def __init__(self):
        import RPi.GPIO as GPIO
        self.GPIO = GPIO
        self.screen = Screen()
        GPIO.setmode(GPIO.BCM)
        for pin in (5, 6):
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        self.display = OLED()
        self.previous, self.stable, self.since = (False, False), (False, False), time.monotonic()
        self.pressed = set()
        self.press_started = None
        self.last_screen = None
        self.suppress_release = False

    def poll(self):
        raw = (not self.GPIO.input(5), not self.GPIO.input(6))
        now = time.monotonic()
        if raw != self.previous:
            self.previous, self.since = raw, now
        if now - self.since < 0.035 or raw == self.stable:
            return None
        self.stable = raw
        if any(raw) and self.press_started is None:
            self.press_started = now
        if raw[0]:
            self.pressed.add("a")
        if raw[1]:
            self.pressed.add("b")
        if not any(raw) and self.pressed:
            held = now - self.press_started if self.press_started is not None else 0
            # Left/right only: a deliberate right hold selects/confirms.
            # Simultaneous presses are ignored so an accidental chord cannot sign.
            key = None if self.suppress_release or len(self.pressed) == 2 else (
                "both" if "b" in self.pressed and held >= 0.9 else
                "cancel" if "a" in self.pressed and held >= 0.9 else next(iter(self.pressed)))
            self.pressed = set()
            self.press_started = None
            self.suppress_release = False
            return key
        return None

    def render(self, screen, **options):
        image = self.screen.render(screen, pressed=self.stable, **options)
        frame = image.tobytes()
        if frame == self.last_screen:
            return
        self.display.show(image)
        self.last_screen = frame

    def close(self):
        self.display.close()
        self.GPIO.cleanup([5, 6])
