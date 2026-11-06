"""Pixel-measured monochrome OLED rendering, also used for offline image tests."""
from PIL import Image, ImageDraw, ImageFont


class Screen:
    WIDTH, HEIGHT = 128, 64

    def __init__(self):
        # Debian's fonts-dejavu-core is installed in the image. Never silently use
        # a different-width fallback for transaction data.
        font = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
        self.small = ImageFont.truetype(font, 8)
        self.body = ImageFont.truetype(font, 9)
        self.large = ImageFont.truetype(font, 12)

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
            self.logo(draw, 56, 3, 15)
            self.center(draw, "SATOOSHI", 23, self.body)
            if title == "SATOOSHI START":
                self.center(draw, "Head over to", 39, self.small)
                self.center(draw, "satooshi.io/start", 51, self.small)
            else:
                self.center(draw, body[0], 39, self.body)
                self.center(draw, "Connect to your wallet", 53, self.small)
            return image  # Home is intentionally free of navigation arrows.
        if phase == "success":
            draw.line([(51, 15), (60, 24), (78, 6)], fill=1, width=2)
            self.center(draw, title, 32, self.body)
            self.center(draw, body[0], 46, self.small)
            return image
        label = title
        # Compact page number is right-aligned; don't overlap heading.
        number = "%d/%d" % (step + 1, steps) if steps else ""
        number_width = draw.textlength(number, font=self.small)
        if draw.textlength(label, font=self.small) > (122 - number_width - (4 if number else 0)):
            raise ValueError("Device title exceeds available pixels")
        draw.text((2, 1), label, font=self.small, fill=1, anchor="lt")
        if number:
            draw.text((126 - number_width, 1), number, font=self.small, fill=1, anchor="lt")
        font = self.small if phase in ("review", "preview_review", "address", "message") else self.body
        lines = []
        for value in body:
            lines.extend(self.wrap(draw, value, font))
        limit = 5 if review_confirmed else 4
        if len(lines) > limit:
            raise ValueError("Device screen overflow; action cannot be safely reviewed")
        spacing, top = (8, 12) if len(lines) == 5 else (9, 14)
        for i, line in enumerate(lines):
            draw.text((2, top + i * spacing), line, font=font, fill=1, anchor="lt")
        if progress > 0:
            draw.rectangle((17, 55, 110, 62), outline=1)
            end = 18 + round(91 * min(1, progress))
            if end > 18:
                draw.rectangle((18, 56, end, 61), fill=1)
        else:
            hint = "Hold right 3s" if review_confirmed else "Hold to confirm"
            if simulated:
                hint = "Preview / hold 3s" if review_confirmed else "Preview / confirm"
            self.center(draw, hint, 56, self.small)
        draw.polygon([(3, 59), (8, 55), (8, 63)], outline=1, fill=1 if pressed[0] else 0)
        draw.polygon([(124, 59), (119, 55), (119, 63)], outline=1, fill=1 if pressed[1] else 0)
        return image
