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
        if kind == "vechain":
            uncompressed = VerifyingKey.from_string(key, curve=SECP256k1).to_string()
            return "0x" + digest(uncompressed)[-20:].hex()
        if kind == "filecoin":
            uncompressed = b"\x04" + VerifyingKey.from_string(key, curve=SECP256k1).to_string()
            payload = hashlib.blake2b(uncompressed, digest_size=20).digest()
            checksum = hashlib.blake2b(b"\x01" + payload, digest_size=4).digest()
            return "f1" + base64.b32encode(payload + checksum).decode().lower().rstrip("=")
        if kind == "zcash":
            return checked(b"\x1c\xb8" + hash160(key))
        if kind in ("cosmos", "celestia", "akash", "fetch"):
            # Cosmos account Bech32, NOT the SegWit witness encoder.
            return bech32.bech32_encode(bech32.Encoding.BECH32, kind, bech32.convertbits(hash160(key), 8, 5))
        if kind == "injective":
            uncompressed = VerifyingKey.from_string(key, curve=SECP256k1).to_string()
            return bech32.bech32_encode(bech32.Encoding.BECH32, "inj", bech32.convertbits(digest(uncompressed)[-20:], 8, 5))
        if kind == "stacks":
            alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
            payload = hash160(key)
            checksum = hashlib.sha256(hashlib.sha256(b"\x16" + payload).digest()).digest()[:4]
            data = payload + checksum
            n, encoded = int.from_bytes(data, "big"), ""
            while n:
                n, digit = divmod(n, 32)
                encoded = alphabet[digit] + encoded
            return "SP" + "0" * (len(data) - len(data.lstrip(b"\0"))) + encoded
        if kind in ("bitcoin", "litecoin"):
            return bech32.encode("bc" if kind == "bitcoin" else "ltc", 0, hash160(key))
        if kind == "dogecoin":
            return checked(b"\x1e" + hash160(key))
        if kind in ("dash", "bsv"):
            return checked((b"\x4c" if kind == "dash" else b"\0") + hash160(key))
        if kind == "xrp":
            return checked(b"\0" + hash160(key), XRP58)
        if kind == "tron":
            uncompressed = VerifyingKey.from_string(key, curve=SECP256k1).to_string()
            return checked(b"\x41" + digest(uncompressed)[-20:])
        if kind == "icp":
            uncompressed = b"\x04" + VerifyingKey.from_string(key, curve=SECP256k1).to_string()
            der = bytes.fromhex("3056301006072a8648ce3d020106052b8104000a034200") + uncompressed
            principal = hashlib.sha224(der).digest() + b"\x02"
            h = hashlib.sha224(b"\x0aaccount-id" + principal + bytes(32)).digest()
            return (binascii.crc32(h).to_bytes(4, "big") + h).hex()
        # Kaspa uses the cashaddr checksum but version-zero 32-byte x-only keys.
        prefix = "kaspa" if kind == "kaspa" else "bitcoincash"
        payload = bech32.convertbits(b"\0" + (key[1:] if kind == "kaspa" else hash160(key)), 8, 5)
        values = [ord(c) & 31 for c in prefix] + [0] + payload + [0] * 8
        checksum = 1
        generators = (0x98f2bc8e61, 0x79b76d99e2, 0xf33e5fb3c4, 0xae2eabe2a8, 0x1e4f43e470)
        for value in values:
            top = checksum >> 35
            checksum = ((checksum & 0x07ffffffff) << 5) ^ value
            for i, generator in enumerate(generators):
                if top >> i & 1:
                    checksum ^= generator
        checksum ^= 1
        return prefix + ":" + "".join(bech32.CHARSET[v] for v in payload + [(checksum >> (5 * (7 - i))) & 31 for i in range(8)])
    if kind in ED_PATHS:
        key = Ed25519PrivateKey.from_private_bytes(_ed_secret(_seed(entropy), kind)).public_key().public_bytes(KeyEncoding.Raw, PublicFormat.Raw)
        if kind == "hedera":
            return "0.0.302a300506032b6570032100" + key.hex()
        if kind == "solana":
            return b58(key)
        if kind == "near":
            return key.hex()
        if kind == "aptos":
            return "0x" + hashlib.sha3_256(key + b"\0").hexdigest()
        if kind == "sui":
            return "0x" + hashlib.blake2b(b"\0" + key, digest_size=32).hexdigest()
        if kind == "algorand":
            return base64.b32encode(key + hashlib.new("sha512_256", key).digest()[-4:]).decode().rstrip("=")
        if kind == "ton":
            # Canonical V4R2: fixed code hash/depth, seqno=0, wallet id,
            # Ed25519 key and empty plugin dictionary. No host-provided code.
            code = bytes.fromhex("feb5ff6820e2ff0d9483e7e0d62c817d846789fb4ae580c878866d959dabd5c0")
            data = bytes(4) + (698983191).to_bytes(4, "big") + key + b"\x40"
            data_hash = hashlib.sha256(b"\x00\x51" + data).digest()
            state_hash = hashlib.sha256(b"\x02\x01\x34\x00\x07\x00\x00" + code + data_hash).digest()
            raw = b"\x51\x00" + state_hash
            return base64.urlsafe_b64encode(raw + binascii.crc_hqx(raw, 0).to_bytes(2, "big")).decode()
        data = b"\x30" + key
        return base64.b32encode(data + binascii.crc_hqx(data, 0).to_bytes(2, "little")).decode().rstrip("=")
    if kind == "cardano":
        keys = [_point(int.from_bytes(_ada_key(entropy, role)[:32], "little")) for role in (0, 2)]
        data = b"\x01" + b"".join(hashlib.blake2b(key, digest_size=28).digest() for key in keys)
        return bech32.bech32_encode(bech32.Encoding.BECH32, "addr", bech32.convertbits(data, 8, 5))
    if kind in ("polkadot", "bittensor"):
        out = ctypes.create_string_buffer(32)
        if _sr().satooshi_public(_mini(entropy), out):
            raise ValueError("Public derivation failed")
        data = (b"\x2a" if kind == "bittensor" else b"\0") + out.raw
        return b58(data + hashlib.blake2b(b"SS58PRE" + data).digest()[:2])
    raise ValueError("Unsupported receive network")
