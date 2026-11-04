"""Device-local storage. Never return entropy, a PIN or words through USB."""
import base64
import json
import os
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

AAD = b"satooshi-pro:vault:1"


class WrongPIN(ValueError):
    def __init__(self, remaining):
        self.remaining = remaining
        super().__init__("Device reset" if remaining == 0 else "Incorrect PIN")


def b64(value):
    return base64.b64encode(value).decode("ascii")


class Vault:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.directory, 0o700)
        self.path = self.directory / "wallet.json"
        self.key_path = self.directory / "device.key"

    @property
    def exists(self):
        return self.path.is_file()

    def metadata(self):
        data = json.loads(self.path.read_text())
        if data.get("version") != 1:
            raise ValueError("Unsupported device vault")
        return data

    def atomic_write(self, path, content):
        temp = path.with_suffix(".tmp")
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "wb") as out:
                out.write(content)
                out.flush()
                os.fsync(out.fileno())
            os.replace(temp, path)
            directory = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            temp.unlink(missing_ok=True)

    def _key(self, pin, salt):
        if pin is not None:
            if not (pin.isascii() and pin.isdigit() and 4 <= len(pin) <= 12):
                raise ValueError("PIN must contain 4–12 digits")
            return Scrypt(salt=salt, length=32, n=2**14, r=8, p=1).derive(pin.encode("ascii"))
        return self.key_path.read_bytes()

    def create(self, entropy, pin):
        if self.exists:
            raise ValueError("A wallet already exists; reset must be confirmed on the device")
        if len(entropy) != 32:
            raise ValueError("24-word entropy required")
        salt, nonce = os.urandom(16), os.urandom(12)
        if pin is None:
            self.atomic_write(self.key_path, os.urandom(32))
        key = self._key(pin, salt)
        data = dict(version=1, salt=b64(salt), nonce=b64(nonce), pin=pin is not None,
                    failed=0, encrypted=b64(AESGCM(key).encrypt(nonce, entropy, AAD)))
        self.atomic_write(self.path, json.dumps(data).encode())

    def unlock(self, pin=None):
        data = self.metadata()
        if data["pin"]:
            # Persist a charged attempt BEFORE validation, including interrupted attempts.
            data["failed"] += 1
            self.atomic_write(self.path, json.dumps(data).encode())
        try:
            key = self._key(pin if data["pin"] else None, base64.b64decode(data["salt"]))
            entropy = AESGCM(key).decrypt(base64.b64decode(data["nonce"]),
                                         base64.b64decode(data["encrypted"]), AAD)
        except (InvalidTag, ValueError, TypeError):
            remaining = max(0, 5 - data["failed"])
            if remaining == 0:
                self.wipe()
            raise WrongPIN(remaining) from None
        data["failed"] = 0
        self.atomic_write(self.path, json.dumps(data).encode())
        return entropy

    def wipe(self):
        # Logical deletion only. Flash controllers can retain old physical blocks.
        for path in (self.path, self.key_path, self.path.with_suffix(".tmp"),
                     self.key_path.with_suffix(".tmp")):
            path.unlink(missing_ok=True)
