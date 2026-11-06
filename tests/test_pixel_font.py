import unittest
from PIL import ImageDraw, Image
from satooshi.pixel_font import GLYPHS, PixelFont


class PixelFontTests(unittest.TestCase):
    def test_ascii_has_spacing_and_never_loses_glyphs(self):
        font = PixelFont()
        for value in range(32, 127):
            char = chr(value)
            self.assertIn(char, GLYPHS)
            mask = Image.new("1", (12, 7))
            ImageDraw.Draw(mask).text((0, 0), char + char, font=font, fill=1)
            self.assertFalse(any(mask.getpixel((5, y)) for y in range(7)), char)
            self.assertEqual(font.getlength(char + char), 12)
            if char != " ":
                self.assertIsNotNone(mask.getbbox(), char)

    def test_unsupported_chars_fail_instead_of_replacing_payment_data(self):
        with self.assertRaises(ValueError):
            PixelFont().getmask("\u2603")
