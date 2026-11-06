"""Physical-button state machine. Sensitive display content never enters USB events."""
import os
import secrets
import time
import textwrap

from .evm import Transfer, WORDLIST, address
from .rehearsal import Rehearsal
from .screen import Screen
from .vault import WrongPIN


class Controller:
    def __init__(self, vault, emit, clock=time.monotonic):
        self.vault, self.emit, self.clock = vault, emit, clock
        self.entropy = None
        self.phase, self.step = "home", 0
        self.pending = None
        self.pin, self.pin_first, self.digit = "", "", 0
        self.pin_mode, self.error = "", ""
        self.last_action = clock()
        self.last_host = clock()
        self.review = None
        self.visited = set()
        self.quiz = []
        self.message = ""
        self.hold_started = None
        self.hold_progress = 0
        self.hold_armed = False
        self.success_until = 0
        self.success_preview = False

    def status(self):
        meta = self.vault.metadata() if self.vault.exists else {}
        return dict(name="Satooshi Pro", version="0.3.0", configured=self.vault.exists,
                    locked=self.entropy is None, phase=self.phase, step=self.step,
                    steps=24 if self.phase == "backup" else len(self.review.pages()) if self.review else 0,
                    attemptsRemaining=max(0, 5 - meta.get("failed", 0)),
                    pinEnabled=meta.get("pin", False), error=self.error,
                    capabilities=["ethereum-native-eip1559", "sepolia-native-eip1559"],
                    previewCapabilities=["send", "swap", "receive", "message"],
                    controls="left-right-hold", confirmHoldMs=3000, prototype=True)

    def changed(self):
        self.emit({"event": "state", "data": self.status()})

    def result(self, data):
        if self.pending is not None:
            self.emit({"event": "result", "data": {"requestId": self.pending, "result": data}})
        self.pending = None

    def cancel(self):
        self.result({"cancelled": True})
        # During setup the unsaved wallet must be forgotten, not left as an unlocked signer.
        if not self.vault.exists:
            self.entropy = None
        self.phase, self.step, self.review = "home", 0, None
        self.hold_started, self.hold_progress, self.hold_armed = None, 0, False
        self.pin = self.pin_first = ""
        self.changed()

    def lock(self):
        self.entropy = None
        self.cancel()

    def request(self, method, params, request_id):
        self.last_host = self.clock()
        if method in ("hello", "status"):
            return self.status()
        if method == "cancel":
            self.cancel()
            return self.status()
        if method == "lock":
            self.lock()
            return self.status()
        if self.pending is not None or self.phase != "home":
            raise ValueError("Complete or cancel the current action on the device")
        if method == "setup":
            if self.vault.exists:
                raise ValueError("Wallet already configured; unlock or physically reset")
            if params:
                raise ValueError("Setup takes no seed or PIN from the computer")
            self.pending, self.phase = request_id, "setup_confirm"
        elif method == "pair":
            if params:
                raise ValueError("Pairing takes no computer-supplied data")
            self.pending, self.phase = request_id, "pair"
        elif method == "unlock":
            if not self.vault.exists:
                raise ValueError("Set up the device first")
            self.pending = request_id
            self.phase = "unlock_confirm"
        elif method == "get_address":
            self.require_unlock()
            if params:
                raise ValueError("Only account 0, Ethereum address is supported")
            self.pending, self.phase = request_id, "address"
        elif method == "review_transfer":
            self.require_unlock()
            self.start_review(Transfer(params), request_id, "review")
        elif method == "preview_review":
            # Explicitly non-signing. May be used before setup; never touches vault.
            self.start_review(Rehearsal(params), request_id, "preview_review")
        elif method == "reset":
            self.pending, self.phase, self.step = request_id, "reset", 0
        elif method == "show_message":
            message = params.get("text")
            if not isinstance(message, str) or not 1 <= len(message) <= 80:
                raise ValueError("Informational message must be 1–80 characters")
            if any(ord(c) < 32 or ord(c) > 126 for c in message):
                raise ValueError("Only printable ASCII messages are supported")
            self.message = message
            self.pending, self.phase = request_id, "message"
        else:
            raise ValueError("Unsupported command")
        self.last_action = self.clock()
        self.error = ""
        self.changed()
        return {"accepted": True}

    def require_unlock(self):
        if self.entropy is None or not self.vault.exists:
            raise ValueError("Unlock the device first")

    def start_review(self, review, request_id, phase):
        # Check every page's actual pixel layout BEFORE accepting the action.
        # Display overflow is a rejected request, never a crash halfway through.
        renderer = Screen()
        pages = review.pages()
        for i, page in enumerate(pages):
            renderer.render((*page, ""), phase=phase, step=i, steps=len(pages),
                            review_confirmed=i == len(pages) - 1,
                            simulated=phase == "preview_review")
        self.review = review
        self.pending, self.phase, self.step = request_id, phase, 0
        self.visited = set()
        self.hold_started, self.hold_progress, self.hold_armed = None, 0, False

    def _begin_pin(self, mode):
        self.phase, self.pin_mode, self.pin, self.digit = "pin", mode, "", 0

    def _finish_pin(self):
        pin = self.pin
        self.pin = ""
        if self.pin_mode == "unlock":
            try:
                self.entropy = self.vault.unlock(pin)
                self.phase = "home"
                self.result({"unlocked": True})
            except WrongPIN as exc:
                self.entropy = None
                self.error = "Device reset" if exc.remaining == 0 else "Incorrect PIN"
                if exc.remaining:
                    self._begin_pin("unlock")
                else:
                    self.phase = "home"
                    self.result({"reset": True})
        elif self.pin_mode == "new":
            self.pin_first = pin
            self._begin_pin("confirm")
        else:
            if pin != self.pin_first:
                self.pin_first = ""
                self.error = "PINs did not match"
                self._begin_pin("new")
            else:
                self.vault.create(self.entropy, pin)
                self.pin_first = ""
                self.phase = "home"
                self.result({"configured": True, "pinEnabled": True})

    def button(self, key):
        if key == "cancel":
            if self.phase != "home":
                self.cancel()
            elif self.entropy is not None:
                self.lock()
            return
        if key not in ("a", "b", "both"):
            return
        self.last_action = self.clock()
        self.error = ""
        phase = self.phase
        if phase == "pair":
            if key == "a":
                self.cancel()
            elif key == "both":
                self.result({"paired": True, "firmware": "0.3.0"})
                self.phase = "home"
        elif phase == "setup_confirm":
            if key == "a":
                self.cancel()
            elif key == "both":
                self.entropy = os.urandom(32)
                self.phase, self.step = "backup", 0
        elif phase == "backup":
            if key == "a":
                self.step = max(0, self.step - 1)
            elif key == "b":
                self.step = min(23, self.step + 1)
            elif self.step == 23:
                self.quiz_positions = sorted(secrets.SystemRandom().sample(range(24), 3))
                self.quiz_index = 0
                self._new_quiz()
                self.phase = "quiz"
        elif phase == "quiz":
            if key == "a":
                self.choice = (self.choice - 1) % 3
            elif key == "b":
                self.choice = (self.choice + 1) % 3
            elif self.quiz[self.choice] == self._words()[self.quiz_positions[self.quiz_index]]:
                self.quiz_index += 1
                if self.quiz_index == 3:
                    self.phase, self.choice = "pin_choice", 0
                else:
                    self._new_quiz()
            else:
                self.error = "Try that word again"
        elif phase == "pin_choice":
            if key in ("a", "b"):
                self.choice = 1 - self.choice
            elif self.choice == 0:
                self._begin_pin("new")
            else:
                self.phase = "no_pin_confirm"
        elif phase == "no_pin_confirm":
            if key == "a":
                self.phase, self.choice = "pin_choice", 0
            elif key == "both":
                self.vault.create(self.entropy, None)
                self.phase = "home"
                self.result({"configured": True, "pinEnabled": False})
        elif phase == "pin":
            # 0..9, finish, delete. Both buttons selects; never sends PIN over USB.
            if key == "a":
                self.digit = (self.digit - 1) % 12
            elif key == "b":
                self.digit = (self.digit + 1) % 12
            elif self.digit == 10:
                if len(self.pin) >= 4:
                    self._finish_pin()
                else:
                    self.error = "Minimum 4 digits"
            elif self.digit == 11:
                self.pin = self.pin[:-1]
            elif len(self.pin) < 12:
                self.pin += str(self.digit)
            else:
                self.error = "Select Done (max 12)"
        elif phase == "unlock_confirm":
            if key == "a":
                self.cancel()
            elif key == "both":
                if self.vault.metadata()["pin"]:
                    self._begin_pin("unlock")
                else:
                    self.entropy = self.vault.unlock()
                    self.phase = "home"
                    self.result({"unlocked": True})
        elif phase == "address":
            if key == "a":
                self.cancel()
            elif key == "both":
                self.result({"address": address(self.entropy), "path": "m/44'/60'/0'/0/0"})
                self.phase = "home"
        elif phase in ("review", "preview_review"):
            last = len(self.review.pages()) - 1
            if key == "a":
                self.step = max(0, self.step - 1)
            elif key in ("b", "both") and self.step < last:
                self.visited.add(self.step)
                self.step += 1
            # Only continuous local GPIO state in hold() can approve the last page.
            self.hold_started, self.hold_progress, self.hold_armed = None, 0, False
        elif phase == "reset":
            if key == "a":
                self.cancel()
            elif key == "both":
                if self.step == 0:
                    self.step = 1
                else:
                    self.vault.wipe()
                    self.entropy = None
                    self.phase, self.step = "home", 0
                    self.result({"reset": True})
        elif phase == "message" and key == "both":
            self.result({"dismissed": True})
            self.phase = "home"
        elif phase == "home" and key == "both" and self.entropy is not None:
            self.lock()
        self.changed()

    def hold(self, right, left=False):
        """Only the local GPIO runtime supplies this, never the USB protocol."""
        if not right or left:
            self.hold_started, self.hold_progress = None, 0
            if left:
                self.hold_armed = False
            if not right and not left:
                self.hold_armed = True
            return
        if self.phase not in ("review", "preview_review") or not self.review:
            return
        last = len(self.review.pages()) - 1
        if self.step != last or not all(i in self.visited for i in range(last)) or not self.hold_armed:
            return
        if self.hold_started is None:
            self.hold_started = self.clock()
        self.hold_progress = min(1, (self.clock() - self.hold_started) / 3)
        self.last_action = self.clock()
        if self.hold_progress < 1:
            return
        preview = self.phase == "preview_review"
        result = self.review.approve() if preview else self.review.sign(self.entropy)
        self.result(result)
        self.review, self.phase, self.step = None, "success", 0
        self.success_preview, self.success_until = preview, self.clock() + 3
        self.hold_started, self.hold_progress, self.hold_armed = None, 0, False
        self.changed()

    def _words(self):
        return WORDLIST.to_mnemonic(self.entropy).split()

    def _new_quiz(self):
        word = self._words()[self.quiz_positions[self.quiz_index]]
        choices = [word] + secrets.SystemRandom().sample(
            [w for w in WORDLIST.wordlist if w != word], 2)
        secrets.SystemRandom().shuffle(choices)
        self.quiz, self.choice = choices, 0

    def tick(self):
        now = self.clock()
        if self.phase == "success" and now >= self.success_until:
            self.phase = "home"
            self.changed()
        if (self.entropy is not None or self.pending is not None) and (
                now - self.last_action > 300 or now - self.last_host > 45):
            self.lock()

    def display(self):
        if self.phase == "backup":
            return ("Recovery word %d/24" % (self.step + 1),
                    [self._words()[self.step], "Write on paper only"], "Left/right; hold right")
        if self.phase == "quiz":
            return ("Check word #%d" % (self.quiz_positions[self.quiz_index] + 1),
                    [self.quiz[self.choice], "%d/3 backup check" % (self.quiz_index + 1)],
                    "Hold right to select")
        if self.phase == "pin":
            title = {"new": "Choose PIN", "confirm": "Repeat PIN", "unlock": "Unlock"}[self.pin_mode]
            selection = str(self.digit) if self.digit < 10 else "Done" if self.digit == 10 else "Delete"
            lines = ["*" * len(self.pin), "> " + selection]
            if self.pin_mode == "unlock":
                lines += ["! %d attempts left" % self.status()["attemptsRemaining"]]
            return title, lines, "Hold right to select"
        if self.phase in ("review", "preview_review"):
            title, lines = self.review.pages()[self.step]
            return title, lines, "Hold right 3s"
        if self.phase == "success":
            return ("Approval complete" if self.success_preview else "Transaction signed",
                    ["No funds moved" if self.success_preview else "Check your wallet"], "")
        if self.phase == "address":
            value = address(self.entropy)
            return "Verify ETH address", [value[:21], value[21:]], "Hold right to confirm"
        if self.phase == "setup_confirm":
            return "Create a wallet?", ["Keys stay here", "Back up all 24 words"], "Hold right to create"
        if self.phase == "pair":
            return "Connect wallet?", ["Satooshi web wallet", "Hold right to pair", "Left to decline"], ""
        if self.phase == "pin_choice":
            return "Protect your wallet", ["> Set a PIN" if self.choice == 0 else "> No PIN"], "Hold right to select"
        if self.phase == "no_pin_confirm":
            return "! No PIN protection", ["Anyone with the device", "can unlock this wallet"], "Hold right to accept"
        if self.phase == "unlock_confirm":
            return "Unlock this wallet?", ["Check your computer"], "Hold right to unlock"
        if self.phase == "reset":
            return "! Reset wallet?" if self.step == 0 else "! FINAL CONFIRMATION", [
                "Deletes device wallet", "Have your paper backup"], "Hold right to reset"
        if self.phase == "message":
            return "From computer", [self.message[i:i + 24] for i in range(0, len(self.message), 24)], "Hold right to close"
        if not self.vault.exists and self.entropy is None:
            return "SATOOSHI START", ["Head over to", "satooshi.io/start"], ""
        return "SATOOSHI PRO", ["Unlocked" if self.entropy is not None else "Locked" if self.vault.exists else "Welcome",
                                 "Your keys. Your wallet.", "Connect to Satooshi"], "Hold right: lock" if self.entropy else "Connect USB to begin"
