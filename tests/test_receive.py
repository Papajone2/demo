import unittest
from unittest.mock import Mock
from PIL import Image
from satooshi.oled import OLED
from satooshi.screen import Screen


class ReceiveDisplayTests(unittest.TestCase):
    def test_backup_review_and_pin_never_draw_hold_progress(self):
        screen = Screen()
        for phase, data in (
            ("backup", ("Word 1 of 24", ["abandon"], "Next word")),
            ("quiz", ("Check word 1/24", ["abandon"], "Next word")),
            ("pin", ("Choose PIN", ["**", "5"], "")),
        ):
            self.assertEqual(screen.render(data, phase=phase, progress=0).tobytes(),
                             screen.render(data, phase=phase, progress=.6).tobytes())

    def test_fast_oled_conversion_matches_every_pixel_of_legacy_layout(self):
        image = Image.new("1", (128, 64))
        for x in range(128):
            for y in range(64):
                image.putpixel((x, y), (x * 13 + y * 7) % 11 < 5)
        expected = [sum(1 << bit for bit in range(8) if image.getpixel((x, page * 8 + bit)))
                    for page in range(8) for x in range(128)]
        oled = OLED.__new__(OLED)
        oled.address, oled.bus, oled.command = 0x3c, Mock(), Mock()
        oled.show(image)
        actual = [v for call in oled.bus.write_i2c_block_data.call_args_list for v in call.args[2]]
        self.assertEqual(actual, expected)
