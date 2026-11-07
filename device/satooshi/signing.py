"""Blind-signing primitives. Recovery material and derived secrets stay here.

Only fixed account-zero paths are supported. Website-supplied review labels
are NOT an independently decoded transaction. Never expose a generic key API.
"""
import ctypes
import hashlib
import hmac
import os

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from ecdsa import SECP256k1, SigningKey, VerifyingKey, util
from ecdsa.curves import Ed25519
from embit import bip32
from .evm import WORDLIST

SECP_PATHS = {
    "evm": "m/44h/60h/0h/0/0", "tron": "m/44h/195h/0h/0/0",
    "bitcoin": "m/84h/0h/0h/0/0", "litecoin": "m/84h/2h/0h/0/0",
    "dogecoin": "m/44h/3h/0h/0/0", "bitcoincash": "m/44h/145h/0h/0/0",
    "xrp": "m/44h/144h/0h/0/0",
}
ED_PATHS = {
    "solana": [44, 501, 0, 0], "stellar": [44, 148, 0],
    "aptos": [44, 637, 0, 0, 0], "sui": [44, 784, 0, 0, 0],
    "near": [44, 397, 0],
}
KINDS = tuple(SECP_PATHS) + tuple(ED_PATHS) + ("cardano", "polkadot")
L = Ed25519.order


def _mac(key, data):
    return hmac.new(key, data, hashlib.sha512).digest()


def _seed(entropy):
    return WORDLIST.to_seed(WORDLIST.to_mnemonic(entropy), passphrase="")


def _ed_secret(seed, kind):
    node = _mac(b"ed25519 seed", seed)
    for index in ED_PATHS[kind]:
        node = _mac(node[32:], b"\0" + node[:32] + (index + 0x80000000).to_bytes(4, "big"))
    return node[:32]


def _point(scalar):
    point = Ed25519.generator * scalar
    return (point.y() | ((point.x() & 1) << 255)).to_bytes(32, "little")


def _ada_root(entropy):
    root = bytearray(hashlib.pbkdf2_hmac("sha512", b"", entropy, 4096, 96))
    root[0] &= 248
    root[31] &= 31
    root[31] |= 64
    return bytes(root)


def _ada_child(key, index):
    kl, kr, chain = key[:32], key[32:64], key[64:]
    hard = index >= 0x80000000
    body = (kl + kr if hard else _point(int.from_bytes(kl, "little"))) + index.to_bytes(4, "little")
    z = _mac(chain, bytes([0 if hard else 2]) + body)
    cc = _mac(chain, bytes([1 if hard else 3]) + body)[32:]
    left = (int.from_bytes(kl, "little") + 8 * int.from_bytes(z[:28], "little")) % (1 << 256)
    right = (int.from_bytes(kr, "little") + int.from_bytes(z[32:], "little")) % (1 << 256)
    return left.to_bytes(32, "little") + right.to_bytes(32, "little") + cc


def _ada_key(entropy, role):
    key = _ada_root(entropy)
    for index in (1852 + 0x80000000, 1815 + 0x80000000, 0x80000000, role, 0):
        key = _ada_child(key, index)
    return key


def _sr():
    # Native Rust Schnorrkel bridge, compiled for ARMv6 by the image workflow.
    lib = ctypes.CDLL(os.environ.get("SATOOSHI_SR25519_LIB", "/opt/satooshi/lib/libsatooshi_sr25519.so"))
    lib.satooshi_public.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    lib.satooshi_sign.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    lib.satooshi_public.restype = lib.satooshi_sign.restype = ctypes.c_int
    return lib


def _mini(entropy):
    # Substrate BIP39 uses entropy, not the mnemonic text, as the KDF input.
    return hashlib.pbkdf2_hmac("sha512", entropy, b"mnemonic", 2048, 64)[:32]


def public_keys(entropy):
    seed = _seed(entropy)
    result = {kind: bip32.HDKey.from_seed(seed).derive(path).key.get_public_key().sec().hex()
              for kind, path in SECP_PATHS.items()}
    result.update({kind: Ed25519PrivateKey.from_private_bytes(_ed_secret(seed, kind)).public_key()
                   .public_bytes(Encoding.Raw, PublicFormat.Raw).hex() for kind in ED_PATHS})
    result["cardano"] = _point(int.from_bytes(_ada_key(entropy, 0)[:32], "little")).hex()
    result["cardanoStake"] = _point(int.from_bytes(_ada_key(entropy, 2)[:32], "little")).hex()
    output = ctypes.create_string_buffer(32)
    if _sr().satooshi_public(_mini(entropy), output) != 0:
        raise ValueError("Polkadot public derivation failed")
    result["polkadot"] = output.raw.hex()
    return result


def sign(entropy, kind, message):
    if kind not in KINDS or not isinstance(message, bytes) or not 1 <= len(message) <= 32768:
        raise ValueError("Unsupported signing payload")
    if kind in SECP_PATHS:
        if len(message) != 32:
            raise ValueError("A 32-byte transaction digest is required")
        key = bip32.HDKey.from_seed(_seed(entropy)).derive(SECP_PATHS[kind]).key.secret
        signer = SigningKey.from_string(key, curve=SECP256k1)
        sig = signer.sign_digest_deterministic(message, hashfunc=hashlib.sha256,
                                               sigencode=util.sigencode_string_canonize)
        candidates = VerifyingKey.from_public_key_recovery_with_digest(sig, message, curve=SECP256k1)
        recovery = next(i for i, candidate in enumerate(candidates)
                        if candidate.to_string() == signer.verifying_key.to_string())
        return {"signature": sig.hex(), "recovery": recovery}
    if kind in ED_PATHS:
        key = Ed25519PrivateKey.from_private_bytes(_ed_secret(_seed(entropy), kind))
        return {"signature": key.sign(message).hex()}
    if kind == "cardano":
        if len(message) != 32:
            raise ValueError("Cardano transaction hash must be 32 bytes")
        key = _ada_key(entropy, 0)
        public = _point(int.from_bytes(key[:32], "little"))
        r = int.from_bytes(hashlib.sha512(key[32:64] + message).digest(), "little") % L
        point = _point(r)
        h = int.from_bytes(hashlib.sha512(point + public + message).digest(), "little") % L
        s = (r + h * int.from_bytes(key[:32], "little")) % L
        return {"signature": (point + s.to_bytes(32, "little")).hex()}
    output = ctypes.create_string_buffer(64)
    if _sr().satooshi_sign(_mini(entropy), message, len(message), output) != 0:
        raise ValueError("Polkadot signing failed")
    return {"signature": output.raw.hex()}
