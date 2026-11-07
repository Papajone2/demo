"""Pixel-measured monochrome OLED rendering, also used for offline image tests."""
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
from .pixel_font import PixelFont


class Screen:
    WIDTH, HEIGHT = 128, 64

    def __init__(self):
        # Debian's fonts-dejavu-core is installed in the image. Never silently use
        # a different-width fallback for transaction data.
        font = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
        self.small = PixelFont()
        self.body = PixelFont()
        self.compact = ImageFont.truetype(font, 8)
        self.large = ImageFont.truetype(font, 12)
        self.title = PixelFont()
        self.readable = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11)
        self.word = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
        self.wordmark = Image.open(Path(__file__).with_name("assets") / "wordmark.png").convert("1")
        self.wordmark = self.wordmark.resize(
            (124, round(self.wordmark.height * 124 / self.wordmark.width)), Image.Resampling.NEAREST)

    @staticmethod
    def logo(draw, x, y, size=16):
        """Original geometric S mark, not another wallet's logo."""
        unit = size / 16
        for points in (
            [(3, 0), (16, 0), (13, 4), (4, 4), (1, 7), (0, 3)],
            [(3, 6), (13, 6), (16, 10), (13, 16), (0, 16), (3, 12), (12, 12), (13, 10)],
        ):
            draw.polygon([(round(x + a * unit), round(y + b * unit)) for a, b in points], fill=1)

    def wrap(self, draw, value, font, width=124):
        lines, current = [], ""
        for char in str(value):
            if draw.textlength(current + char, font=font) > width:
                if not current:
                    raise ValueError("Glyph exceeds device screen")
                lines.append(current)
                current = ""
            current += char
        return lines + [current]

    def center(self, draw, value, y, font):
        width = draw.textlength(value, font=font)
        if width > 124:
            raise ValueError("Centered text exceeds device screen")
        draw.text(((128 - width) / 2, y), value, font=font, fill=1, anchor="lt")

    def render(self, screen, phase="home", step=0, steps=0, pressed=(False, False),
               progress=0, review_confirmed=False, simulated=False):
        title, body, footer = screen
        image = Image.new("1", (128, 64))
        draw = ImageDraw.Draw(image)
        if phase == "home":
            image.paste(self.wordmark, ((128 - self.wordmark.width) // 2,
                                       8 if title == "SATOOSHI START" else (64 - self.wordmark.height) // 2))
            if title == "SATOOSHI START":
                self.center(draw, "Head over to", 38, self.title)
                self.center(draw, "satooshi.io/start", 51, self.title)
            return image  # Home is intentionally free of navigation arrows.
        if phase in ("setup_confirm", "pin_choice", "unlock_confirm", "no_pin_confirm", "wallet_open"):
            self.center(draw, title, 7, self.readable)
            self.center(draw, body[0], 25, self.title)
            labels = ("Recover", "New wallet") if phase == "setup_confirm" else (
                ("No", "Yes") if phase == "pin_choice" else ("Back", "Confirm"))
            self.buttons(draw, labels, pressed)
            return image
        if phase in ("backup", "quiz", "recover"):
            self.center(draw, title, 2, self.title)
            self.center(draw, body[0], 22, self.word)
            if phase == "recover":
                self.hold_bar(image, draw, progress, "Hold right 1s")
            else:
                self.center(draw, footer, 49, self.small)
            self.arrows(draw, pressed)
            return image
        if phase == "pin":
            self.center(draw, title, 1, self.title)
            self.center(draw, body[0] or "_", 14, self.body)
            selected = int(body[1])
            # Ten easily readable digits in one row; Done/Delete remain explicit.
            for digit in range(10):
                x = 5 + digit * 12
                draw.text((x, 28), str(digit), font=self.readable, fill=1, anchor="lt")
                if digit == selected:
                    draw.line((x, 41, x + 7, 41), fill=1)
            draw.text((6, 44), "Done", font=self.small, fill=1, anchor="lt")
            draw.text((88, 44), "Delete", font=self.small, fill=1, anchor="lt")
            if selected in (10, 11):
                x, width = (6, 20) if selected == 10 else (88, 29)
                draw.line((x, 52, x + width, 52), fill=1)
            self.center(draw, "Hold right 1s", 55, self.small)
            self.arrows(draw, pressed)
            return image
        if phase == "receive_address":
            self.center(draw, title, 0, self.title)
            self.center(draw, body[0][:18], 13, self.small)
            for i, line in enumerate(body[1:]):
                self.center(draw, line, 25 + i * 12, self.body)
            self.buttons(draw, ("Back", footer), pressed)
            return image
        if phase == "success":
            draw.line([(51, 15), (60, 24), (78, 6)], fill=1, width=2)
            self.center(draw, title, 32, self.body)
            self.center(draw, body[0], 46, self.small)
            return image
        label = title
        # Compact page number is right-aligned; don't overlap heading.
        number = "%d/%d" % (step + 1, steps) if steps else ""
        number_width = draw.textlength(number, font=self.small)
        if draw.textlength(label, font=self.title) > (122 - number_width - (4 if number else 0)):
            raise ValueError("Device title exceeds available pixels")
        draw.text((2, 1), label, font=self.title, fill=1, anchor="lt")
        if number:
            draw.text((126 - number_width, 1), number, font=self.small, fill=1, anchor="lt")
        font = self.body if phase in ("review", "preview_review", "browser_review", "browser_review_release", "address", "message") else self.readable
        if phase == "message":
            font = self.small
        if review_confirmed and any(draw.textlength(str(value), font=font) > 124 for value in body):
            font = self.compact
        lines = []
        for value in body:
            lines.extend(self.wrap(draw, value, font))
        limit = 4
        if len(lines) > limit:
            raise ValueError("Device screen overflow; action cannot be safely reviewed")
        spacing, top = (9, 14)
        for i, line in enumerate(lines):
            draw.text((2, top + i * spacing), line, font=font, fill=1, anchor="lt")
        if phase in ("browser_review", "browser_review_release"):
            self.buttons(draw, ("Back", "Confirm"), pressed)
        elif progress > 0:
            self.hold_bar(image, draw, progress, "Hold right 1s")
        else:
            hint = "Hold right 1s" if review_confirmed else "Hold to confirm"
            if simulated:
                hint = "Preview / hold 1s" if review_confirmed else "Preview / confirm"
            self.center(draw, hint, 56, self.small)
        if phase not in ("browser_review", "browser_review_release"):
            self.arrows(draw, pressed)
        return image

    def buttons(self, draw, labels, pressed):
        for x, label, active in ((1, labels[0], pressed[0]), (65, labels[1], pressed[1])):
            draw.rounded_rectangle((x, 50, x + 61, 63), radius=3, outline=1, fill=1 if active else 0)
            width = draw.textlength(label, font=self.title)
            draw.text((x + (61 - width) / 2, 52), label, font=self.title,
                      fill=0 if active else 1, anchor="lt")

    def arrows(self, draw, pressed):
        draw.polygon([(3, 59), (8, 55), (8, 63)], outline=1, fill=1 if pressed[0] else 0)
        draw.polygon([(124, 59), (119, 55), (119, 63)], outline=1, fill=1 if pressed[1] else 0)

    def hold_bar(self, image, draw, progress, text):
        # The text stays legible as the white progress fill crosses it.
        draw.rectangle((14, 54, 113, 63), outline=1, fill=0)
        end = 15 + round(97 * min(1, progress))
        if progress > 0:
            draw.rectangle((15, 55, end, 62), fill=1)
        mask = Image.new("1", image.size)
        md = ImageDraw.Draw(mask)
        width = md.textlength(text, font=self.small)
        md.text(((128 - width) / 2, 55), text, font=self.small, fill=1, anchor="lt")
        for y in range(55, 63):
            for x in range(15, 113):
                if mask.getpixel((x, y)):
                    image.putpixel((x, y), 0 if image.getpixel((x, y)) else 1)
