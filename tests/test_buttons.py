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
        self.assertIsNone(self.poll((False, True), 2.1))
        self.poll((False, False), 0.01)
        self.assertEqual(self.poll((False, False), 0.04), "both")

    def test_left_hold_cancels(self):
        self.assertEqual(self.press((True, False), 2.1), "cancel")

    def test_simultaneous_buttons_do_not_confirm(self):
        self.assertIsNone(self.press((True, True), 2.1))

    def test_timing_state_resets_after_release(self):
        self.assertEqual(self.press((False, True), 2.1), "both")
        self.assertEqual(self.press((False, True), 0.1), "b")

    def test_navigation_fires_on_press_without_a_hold_or_duplicate_release(self):
        self.raw = (False, True)
        with patch("satooshi.hardware.time.monotonic", return_value=10):
            self.bonnet.poll(hold_select=False)
        with patch("satooshi.hardware.time.monotonic", return_value=10.009):
            self.assertEqual(self.bonnet.poll(hold_select=False), "b")
        self.assertIsNone(self.poll((False, False), 0.02))
        self.assertIsNone(self.poll((False, False), 0.02))


if __name__ == "__main__":
    unittest.main()
