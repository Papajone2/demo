"""Physical review and pixel renderer regressions; all addresses are fixtures."""
import copy
import tempfile
import unittest
from unittest.mock import patch

from satooshi.controller import Controller
from satooshi.evm import Transfer
from satooshi.rehearsal import Rehearsal
from satooshi.screen import Screen
from satooshi.vault import Vault

PAYLOAD = dict(operation="send", amount="10", symbol="TRX",
               address="T" + "1" * 33, fee="1.2", feeSymbol="TRX", network="Tron")


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.events = []
        self.now = 100
        self.device = Controller(Vault(self.tmp.name), self.events.append, clock=lambda: self.now)

    def tearDown(self):
        self.tmp.cleanup()

    def results(self):
        return [e["data"]["result"] for e in self.events if e["event"] == "result"]

    def ready(self, operation="send"):
        p = dict(PAYLOAD, operation=operation)
        if operation == "swap":
            p.update(receiveAmount="0.00001", receiveSymbol="BTC")
        self.device.request("preview_review", p, "preview")
        for _ in range(len(self.device.review.pages()) - 1):
            self.device.button("b")
        self.device.hold(False)

    def test_all_preview_operations_never_sign_or_create_wallet(self):
        for op in ("send", "swap", "receive"):
            with self.subTest(op=op), patch.object(Transfer, "sign", side_effect=AssertionError("Signer called")):
                self.events.clear()
                self.ready(op)
                self.device.hold(True)
                self.now += 3
                self.device.hold(True)
                self.assertEqual(self.results(), [dict(simulated=True, approved=True, operation=op)])
                self.assertFalse(self.device.vault.exists)
                self.assertIsNone(self.device.entropy)
                self.now += 3
                self.device.tick()

    def test_short_hold_and_old_confirmation_do_not_approve(self):
        self.ready()
        self.device.hold(True)
        self.now += 2.99
        self.device.hold(True)
        self.assertLess(self.device.hold_progress, 1)
        self.assertEqual(self.results(), [])
        self.device.hold(False)
        self.assertEqual(self.device.hold_progress, 0)
        self.device.button("both")
        self.assertEqual(self.results(), [])

    def test_release_restarts_three_seconds(self):
        self.ready()
        self.device.hold(True)
        self.now += 2
        self.device.hold(True)
        self.device.hold(False)
        self.device.hold(True)
        self.now += 2
        self.device.hold(True)
        self.assertEqual(self.results(), [])
        self.now += 1
        self.device.hold(True)
        self.assertEqual(len(self.results()), 1)
        self.device.hold(True)
        self.assertEqual(len(self.results()), 1)

    def test_left_or_simultaneous_press_resets_hold(self):
        self.ready()
        self.device.hold(True)
        self.now += 2
        self.device.hold(True, True)
        self.assertEqual(self.device.hold_progress, 0)
        self.now += 2
        self.device.hold(True)
        self.assertEqual(self.results(), [])

    def test_hold_must_start_after_final_page_released(self):
        self.ready()
        self.device.hold_armed = False
        self.device.hold(True)
        self.now += 4
        self.device.hold(True)
        self.assertEqual(self.results(), [])
        self.device.hold(False)
        self.device.hold(True)
        self.now += 3
        self.device.hold(True)
        self.assertEqual(len(self.results()), 1)

    def test_unreviewed_pages_and_usb_methods_cannot_approve(self):
        self.device.request("preview_review", PAYLOAD, "preview")
        self.device.step = len(self.device.review.pages()) - 1
        self.device.hold(False)
        self.device.hold(True)
        self.now += 4
        self.device.hold(True)
        self.assertEqual(self.results(), [])
        for method in ("hold", "button", "approve", "confirm"):
            with self.assertRaises(ValueError):
                self.device.request(method, {}, method)

    def test_cancel_and_disconnect_clear_pending_hold(self):
        self.ready()
        self.device.hold(True)
        self.now += 46
        self.device.tick()
        self.assertIsNone(self.device.review)
        self.assertEqual(self.device.phase, "home")
        self.assertEqual(self.results(), [{"cancelled": True}])

    def test_rehearsal_snapshot_and_validation(self):
        p = copy.deepcopy(PAYLOAD)
        r = Rehearsal(p)
        p["amount"] = "99"
        self.assertEqual(r.data["amount"], "10")
        for field, bad in (("amount", "-1"), ("amount", "NaN"), ("amount", "1e4"),
                           ("amount", "0"), ("fee", "-1"), ("symbol", "BTC\n"),
                           ("symbol", "btc"), ("network", "a" * 49),
                           ("address", "b" * 197), ("address", "Approve all payments")):
            with self.subTest(field=field, bad=bad), self.assertRaises(ValueError):
                Rehearsal({**PAYLOAD, field: bad})
        with self.assertRaises(ValueError):
            Rehearsal({**PAYLOAD, "rawTransaction": "fake"})

    def test_busy_host_cannot_replace_review_or_show_a_message(self):
        self.ready()
        original = self.device.review
        for method, data in (("preview_review", PAYLOAD), ("show_message", {"text": "Approved"})):
            with self.assertRaises(ValueError):
                self.device.request(method, data, "replace")
        self.assertIs(self.device.review, original)

    def test_pairing_automatically_confirms_without_private_data(self):
        self.device.request("pair", {}, "pair")
        self.assertEqual(self.results(), [{"paired": True, "firmware": "0.3.0"}])
        self.assertEqual(self.device.phase, "home")
        self.assertFalse(self.device.vault.exists)


class PixelTests(unittest.TestCase):
    def setUp(self):
        self.screen = Screen()

    def test_home_has_logo_and_no_bottom_corner_arrows(self):
        for title in ("SATOOSHI START", "SATOOSHI PRO"):
            image = self.screen.render((title, ["Locked"], ""), phase="home")
            self.assertIsNone(image.crop((0, 54, 9, 64)).getbbox())
            self.assertIsNone(image.crop((119, 54, 128, 64)).getbbox())
            self.assertIsNotNone(image.getbbox())

    def test_pressed_arrow_and_hold_bar_change_pixels(self):
        screen = ("Confirm send", ["10 TRX", "T111...1111", "1.2 TRX fee"], "")
        a = self.screen.render(screen, phase="preview_review", review_confirmed=True)
        b = self.screen.render(screen, phase="preview_review", review_confirmed=True,
                               pressed=(False, True), progress=0.5)
        self.assertNotEqual(a.crop((118, 54, 128, 64)).tobytes(),
                            b.crop((118, 54, 128, 64)).tobytes())
        self.assertNotEqual(a.crop((17, 55, 110, 64)).tobytes(),
                            b.crop((17, 55, 110, 64)).tobytes())

    def test_all_preview_pages_fit_including_long_addresses_and_amounts(self):
        for op in ("send", "swap", "receive"):
            p = dict(PAYLOAD, operation=op, address="1" * 96, amount="0.0000000000000001",
                     fee="0.0000000000000001", symbol="ABCDE", feeSymbol="ABCDE")
            if op == "swap":
                p.update(receiveAmount="0.00000001", receiveSymbol="BTC")
            review = Rehearsal(p)
            pages = review.pages()
            for i, page in enumerate(pages):
                image = self.screen.render((*page, ""), phase="preview_review",
                                           step=i, steps=len(pages), review_confirmed=i == len(pages) - 1,
                                           simulated=True)
                self.assertEqual(image.size, (128, 64))
            self.assertEqual("".join(line for title, lines in pages if title == "Check address" for line in lines), p["address"])

    def test_overflow_is_an_error_not_silent_clipping(self):
        with self.assertRaises(ValueError):
            self.screen.render(("Review", ["X" * 200], ""), phase="review")


if __name__ == "__main__":
    unittest.main()
