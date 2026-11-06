"""Physical button timing simulation: no Raspberry Pi or GPIO required."""
import unittest
from unittest.mock import patch
from satooshi.hardware import Bonnet


class ButtonTests(unittest.TestCase):
    def setUp(self):
        self.bonnet = Bonnet.__new__(Bonnet)
        self.bonnet.previous = self.bonnet.stable = (False, False)
        self.bonnet.since = 0
        self.bonnet.pressed = set()
        self.bonnet.press_started = None
        self.bonnet.suppress_release = False
        self.now = 10
        self.raw = (False, False)
        class GPIO:
            pass
        self.bonnet.GPIO = GPIO()
        self.bonnet.GPIO.input = lambda pin: not self.raw[0 if pin == 5 else 1]

    def poll(self, raw, duration):
        self.raw = raw
        self.now += duration
        with patch("satooshi.hardware.time.monotonic", return_value=self.now):
            return self.bonnet.poll()

    def press(self, raw, duration):
        self.poll(raw, 0.01)
        self.poll(raw, 0.04)
        self.poll(raw, duration)
        self.poll((False, False), 0.01)
        return self.poll((False, False), 0.04)

    def test_taps_navigate_and_do_not_confirm(self):
        self.assertEqual(self.press((True, False), 0.1), "a")
        self.assertEqual(self.press((False, True), 0.1), "b")

    def test_right_hold_confirms_only_after_release(self):
        self.poll((False, True), 0.01)
        self.poll((False, True), 0.04)
        self.assertIsNone(self.poll((False, True), 1.1))
        self.poll((False, False), 0.01)
        self.assertEqual(self.poll((False, False), 0.04), "both")

    def test_left_hold_cancels(self):
        self.assertEqual(self.press((True, False), 1.1), "cancel")

    def test_simultaneous_buttons_do_not_confirm(self):
        self.assertIsNone(self.press((True, True), 1.1))

    def test_timing_state_resets_after_release(self):
        self.assertEqual(self.press((False, True), 1.1), "both")
        self.assertEqual(self.press((False, True), 0.1), "b")


if __name__ == "__main__":
    unittest.main()
