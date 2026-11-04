"""Physical-button state machine. Sensitive display content never enters USB events."""
import os
import secrets
import time
import textwrap

from .evm import Transfer, WORDLIST, address
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

    def status(self):
        meta = self.vault.metadata() if self.vault.exists else {}
        return dict(name="Satooshi Pro", version="0.1.0", configured=self.vault.exists,
                    locked=self.entropy is None, phase=self.phase, step=self.step,
                    steps=24 if self.phase == "backup" else len(self.review.pages()) if self.review else 0,
                    attemptsRemaining=max(0, 5 - meta.get("failed", 0)),
                    pinEnabled=meta.get("pin", False), error=self.error,
                    capabilities=["ethereum-native-eip1559", "sepolia-native-eip1559"],
                    prototype=True)

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
            self.review = Transfer(params)
            self.pending, self.phase, self.step = request_id, "review", 0
            self.visited = {0}
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
        if key not in ("a", "b", "both"):
            return
        self.last_action = self.clock()
        self.error = ""
        phase = self.phase
        if phase == "setup_confirm":
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
        elif phase == "review":
            last = len(self.review.pages()) - 1
            if key == "a":
                self.step = max(0, self.step - 1)
            elif key == "b":
                if self.step == last:
                    self.cancel()
                else:
                    self.step += 1
                    self.visited.add(self.step)
            elif self.step == last and len(self.visited) == last + 1:
                # Snapshot is owned by the device; host cannot edit a pending review.
                signed = self.review.sign(self.entropy)
                self.result(signed)
                self.review, self.phase, self.step = None, "home", 0
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
        if self.entropy is not None and (now - self.last_action > 300 or now - self.last_host > 45):
            self.lock()

    def display(self):
        if self.phase == "backup":
            return ("Recovery word %d/24" % (self.step + 1),
                    [self._words()[self.step], "Write on paper only"], "A back B next / both OK")
        if self.phase == "quiz":
            return ("Check word #%d" % (self.quiz_positions[self.quiz_index] + 1),
                    [self.quiz[self.choice], "%d/3 backup check" % (self.quiz_index + 1)],
                    "A/B choose Both confirm")
        if self.phase == "pin":
            title = {"new": "Choose PIN", "confirm": "Repeat PIN", "unlock": "Unlock"}[self.pin_mode]
            selection = str(self.digit) if self.digit < 10 else "Done" if self.digit == 10 else "Delete"
            lines = ["*" * len(self.pin), "> " + selection]
            if self.pin_mode == "unlock":
                lines += ["! %d attempts left" % self.status()["attemptsRemaining"]]
            return title, lines, "A/B choose Both select"
        if self.phase == "review":
            title, lines = self.review.pages()[self.step]
            return title, lines, "A back B next Both OK"
        if self.phase == "address":
            value = address(self.entropy)
            return "Verify ETH address", [value[:21], value[21:]], "A cancel Both confirm"
        if self.phase == "setup_confirm":
            return "Create a new wallet?", ["DIY PROTOTYPE", "Test funds only"], "A cancel Both create"
        if self.phase == "pin_choice":
            return "Protect your wallet", ["> Set a PIN" if self.choice == 0 else "> No PIN"], "A/B choose Both OK"
        if self.phase == "no_pin_confirm":
            return "! No PIN protection", ["Anyone with the device", "can unlock this wallet"], "A back Both accept"
        if self.phase == "unlock_confirm":
            return "Unlock this wallet?", ["Check your computer"], "A cancel Both unlock"
        if self.phase == "reset":
            return "! Reset wallet?" if self.step == 0 else "! FINAL CONFIRMATION", [
                "Deletes device wallet", "Have your paper backup"], "A cancel Both reset"
        if self.phase == "message":
            return "COMPUTER MESSAGE", [self.message[i:i + 21] for i in range(0, len(self.message), 21)], "INFO ONLY / Both close"
        return "SATOOSHI PRO", ["Unlocked" if self.entropy is not None else "Locked" if self.vault.exists else "Welcome",
                                 "satooshi.io/start", "DIY prototype"], "Both: lock" if self.entropy else "Connect USB to begin"
