"""Derive receive addresses locally. Never trust a host-supplied destination."""
import base64
import binascii
import ctypes
import hashlib
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding as KeyEncoding, PublicFormat
from ecdsa import SECP256k1, VerifyingKey
from embit import bip32, bech32
from .evm import address, digest
from .signing import SECP_PATHS, ED_PATHS, _seed, _ed_secret, _ada_key, _point, _sr, _mini

BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
XRP58 = "rpshnaf39wBUDNEGHJKLM4PQRST7VWXYZ2bcdeCg65jkm8oFqi1tuvAxyz"


def b58(data, alphabet=BASE58):
    number, out = int.from_bytes(data, "big"), ""
    while number:
        number, digit = divmod(number, 58)
        out = alphabet[digit] + out
    return alphabet[0] * (len(data) - len(data.lstrip(b"\0"))) + out


def checked(data, alphabet=BASE58):
    return b58(data + hashlib.sha256(hashlib.sha256(data).digest()).digest()[:4], alphabet)


def hash160(data):
    return hashlib.new("ripemd160", hashlib.sha256(data).digest()).digest()


def receive_address(entropy, kind):
    if kind == "evm":
        return address(entropy)
    if kind in SECP_PATHS:
        key = bip32.HDKey.from_seed(_seed(entropy)).derive(SECP_PATHS[kind]).key.get_public_key().sec()
        if kind in ("cosmos", "celestia", "akash", "fetch"):
            # Cosmos account Bech32, NOT the SegWit witness encoder.
            return bech32.bech32_encode(bech32.Encoding.BECH32, kind, bech32.convertbits(hash160(key), 8, 5))
        if kind in ("bitcoin", "litecoin"):
            return bech32.encode("bc" if kind == "bitcoin" else "ltc", 0, hash160(key))
        if kind == "dogecoin":
            return checked(b"\x1e" + hash160(key))
        if kind == "xrp":
            return checked(b"\0" + hash160(key), XRP58)
        if kind == "tron":
            uncompressed = VerifyingKey.from_string(key, curve=SECP256k1).to_string()
            return checked(b"\x41" + digest(uncompressed)[-20:])
        # Bitcoin Cash cashaddr P2PKH, version zero and 160-bit key hash.
        payload = bech32.convertbits(b"\0" + hash160(key), 8, 5)
        values = [ord(c) & 31 for c in "bitcoincash"] + [0] + payload + [0] * 8
        checksum = 1
        generators = (0x98f2bc8e61, 0x79b76d99e2, 0xf33e5fb3c4, 0xae2eabe2a8, 0x1e4f43e470)
        for value in values:
            top = checksum >> 35
            checksum = ((checksum & 0x07ffffffff) << 5) ^ value
            for i, generator in enumerate(generators):
                if top >> i & 1:
                    checksum ^= generator
        checksum ^= 1
        return "bitcoincash:" + "".join(bech32.CHARSET[v] for v in payload + [(checksum >> (5 * (7 - i))) & 31 for i in range(8)])
    if kind in ED_PATHS:
        key = Ed25519PrivateKey.from_private_bytes(_ed_secret(_seed(entropy), kind)).public_key().public_bytes(KeyEncoding.Raw, PublicFormat.Raw)
        if kind == "solana":
            return b58(key)
        if kind == "near":
            return key.hex()
        if kind == "aptos":
            return "0x" + hashlib.sha3_256(key + b"\0").hexdigest()
        if kind == "sui":
            return "0x" + hashlib.blake2b(b"\0" + key, digest_size=32).hexdigest()
        data = b"\x30" + key
        return base64.b32encode(data + binascii.crc_hqx(data, 0).to_bytes(2, "little")).decode().rstrip("=")
    if kind == "cardano":
        keys = [_point(int.from_bytes(_ada_key(entropy, role)[:32], "little")) for role in (0, 2)]
        data = b"\x01" + b"".join(hashlib.blake2b(key, digest_size=28).digest() for key in keys)
        return bech32.bech32_encode(bech32.Encoding.BECH32, "addr", bech32.convertbits(data, 8, 5))
    if kind == "polkadot":
        out = ctypes.create_string_buffer(32)
        if _sr().satooshi_public(_mini(entropy), out):
            raise ValueError("Public derivation failed")
        data = b"\0" + out.raw
        return b58(data + hashlib.blake2b(b"SS58PRE" + data).digest()[:2])
    raise ValueError("Unsupported receive network")
