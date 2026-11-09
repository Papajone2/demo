"""Build-time ARM checks only. Never runs on a user's normal wallet boot."""
import ctypes
import importlib.machinery
import importlib.util
from pathlib import Path
import serial
import smbus
from mnemonic import Mnemonic
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from satooshi.signing import public_keys, sign
from satooshi.screen import Screen
from satooshi.oled import OLED
from satooshi.evm import address

# Load the retained upstream ARMv6 binary on the emulated ARM1176, not just
# embit's pure-Python fallback, so packaging cannot silently remove it.
import embit
embit_libraries = Path(embit.__file__).parent / "util/prebuilt"
assert sorted(p.name for p in embit_libraries.iterdir()) == ["libsecp256k1_linux_armv6l.so"]
ctypes.CDLL(str(embit_libraries / "libsecp256k1_linux_armv6l.so"))

assert Mnemonic("english").check(Mnemonic("english").to_mnemonic(bytes(32)))
assert address(bytes(32)) == "0xF278cF59F82eDcf871d630F28EcC8056f25C1cdb"
keys = public_keys(bytes(32))
assert len(keys["polkadot"]) == 64
assert len(sign(bytes(32), "polkadot", b"minimal-image-preflight")["signature"]) == 128
aes = AESGCM(bytes(32))
assert aes.decrypt(bytes(12), aes.encrypt(bytes(12), b"fixture", None), None) == b"fixture"
# Load the actual GPIO extension without invoking its physical-board init hook.
gpio = importlib.util.find_spec("RPi._GPIO")
assert gpio and gpio.origin and isinstance(gpio.loader, importlib.machinery.ExtensionFileLoader)
ctypes.CDLL(gpio.origin)
frame = OLED.frame_bytes(Screen().render(("SATOOSHI LOGO", [], ""), phase="loading"))
assert len(frame) == 1024 and any(frame)
Path("/opt/satooshi/device/satooshi/assets/splash.bin").write_bytes(frame)
print("Target ARMv6 Python, crypto, GPIO ABI, fonts and logo preflight passed.")
