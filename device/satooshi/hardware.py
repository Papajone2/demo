"""Provisional Adafruit 3531: SSD1306 128x64 I2C, A=BCM5 B=BCM6.

No joystick pins are initialized. Failure is explicit, not a simulated device.
"""
import time
from .screen import Screen


class Bonnet:
    def __init__(self):
        import RPi.GPIO as GPIO
        import smbus
        self.GPIO = GPIO
        self.screen = Screen()
        GPIO.setmode(GPIO.BCM)
        for pin in (5, 6):
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        self.bus = smbus.SMBus(1)
        self.address = 0x3c
        # SSD1306 128x64 charge-pump initialization, horizontal addressing.
        for command in (0xae, 0xd5, 0x80, 0xa8, 0x3f, 0xd3, 0, 0x40,
                        0x8d, 0x14, 0x20, 0, 0xa1, 0xc8, 0xda, 0x12,
                        0x81, 0x7f, 0xd9, 0xf1, 0xdb, 0x40, 0xa4, 0xa6, 0xaf):
            self.command(command)
        self.previous, self.stable, self.since = (False, False), (False, False), time.monotonic()
        self.pressed = set()
        self.press_started = None
        self.last_screen = None
        self.suppress_release = False

    def command(self, value):
        self.bus.write_byte_data(self.address, 0, value)

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
        self.command(0x21)
        self.command(0)
        self.command(127)
        self.command(0x22)
        self.command(0)
        self.command(7)
        data = []
        for page in range(8):
            for x in range(128):
                data.append(sum((1 << bit) if image.getpixel((x, page * 8 + bit)) else 0
                                for bit in range(8)))
        for start in range(0, len(data), 32):
            self.bus.write_i2c_block_data(self.address, 0x40, data[start:start + 32])
        self.last_screen = frame

    def close(self):
        self.command(0xae)
        self.bus.close()
        self.GPIO.cleanup([5, 6])
