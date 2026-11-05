"""Provisional Adafruit 3531: SSD1306 128x64 I2C, A=BCM5 B=BCM6.

No joystick pins are initialized. Failure is explicit, not a simulated device.
"""
import textwrap
import time


class Bonnet:
    def __init__(self):
        import RPi.GPIO as GPIO
        import smbus
        from PIL import Image, ImageDraw, ImageFont
        self.GPIO, self.Image, self.ImageDraw = GPIO, Image, ImageDraw
        self.font = ImageFont.load_default()
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
            key = None if len(self.pressed) == 2 else (
                "both" if "b" in self.pressed and held >= 0.9 else
                "cancel" if "a" in self.pressed and held >= 0.9 else next(iter(self.pressed)))
            self.pressed = set()
            self.press_started = None
            return key
        return None

    def render(self, screen):
        if screen == self.last_screen:
            return
        title, body, footer = screen
        image = self.Image.new("1", (128, 64))
        draw = self.ImageDraw.Draw(image)
        if title == "SATOOSHI START":
            # Replace this neutral mark with the user's logo when provided.
            draw.rectangle((56, 6, 71, 21), fill=1)
            for y, line in ((29, "Head over to"), (41, "satooshi.io/start")):
                bounds = draw.textbbox((0, 0), line, font=self.font)
                draw.text(((128 - (bounds[2] - bounds[0])) // 2, y), line,
                          font=self.font, fill=1)
        else:
            draw.text((1, 0), title[:21], font=self.font, fill=1)
            lines = []
            for line in body:
                lines.extend(textwrap.wrap(str(line), width=21, break_long_words=True,
                                           break_on_hyphens=False) or [""])
            if len(lines) > 4:
                # Never truncate a transaction or recovery word.
                raise ValueError("Device screen overflow; action cannot be safely reviewed")
            for i, line in enumerate(lines):
                draw.text((1, 12 + i * 10), line, font=self.font, fill=1)
        # Dedicated footer: no crowded A/B instructions, only physical directions.
        draw.polygon([(3, 59), (8, 55), (8, 63)], fill=1)
        draw.polygon([(124, 59), (119, 55), (119, 63)], fill=1)
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
        self.last_screen = screen

    def close(self):
        self.command(0xae)
        self.bus.close()
        self.GPIO.cleanup([5, 6])
