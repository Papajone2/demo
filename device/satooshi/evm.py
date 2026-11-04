"""BIP39/BIP32 keys and strictly decoded EIP-1559 native ETH transfers.

No blind signing, arbitrary hashes, contract calls, messages, or host-selected paths.
"""
import hashlib
import re
from decimal import Decimal

from ecdsa import SECP256k1, SigningKey, VerifyingKey, util
from embit import bip32
from mnemonic import Mnemonic
try:
    from Crypto.Hash import keccak
except ImportError:  # Raspberry Pi OS's Debian package uses this namespace.
    from Cryptodome.Hash import keccak

CHAINS = {1: "Ethereum / real ETH", 11155111: "Sepolia / test ETH"}
WORDLIST = Mnemonic("english")


def digest(data):
    h = keccak.new(digest_bits=256)
    h.update(data)
    return h.digest()


def private_key(entropy):
    seed = WORDLIST.to_seed(WORDLIST.to_mnemonic(entropy), passphrase="")
    return bip32.HDKey.from_seed(seed).derive("m/44h/60h/0h/0/0").key.secret


def checksum_address(raw):
    lower = raw.hex()
    hashed = digest(lower.encode("ascii")).hex()
    return "0x" + "".join(c.upper() if int(hashed[i], 16) >= 8 else c
                         for i, c in enumerate(lower))


def address(entropy):
    key = SigningKey.from_string(private_key(entropy), curve=SECP256k1)
    return checksum_address(digest(key.verifying_key.to_string())[-20:])


def rlp(item):
    if isinstance(item, int):
        if item < 0:
            raise ValueError("Negative RLP integer")
        return rlp(item.to_bytes((item.bit_length() + 7) // 8, "big"))
    if isinstance(item, (list, tuple)):
        data = b"".join(rlp(v) for v in item)
        offset = 0xc0
    elif isinstance(item, bytes):
        data, offset = item, 0x80
        if len(data) == 1 and data[0] < 0x80:
            return data
    else:
        raise ValueError("Unsupported RLP value")
    if len(data) <= 55:
        return bytes([offset + len(data)]) + data
    length = len(data).to_bytes((len(data).bit_length() + 7) // 8, "big")
    return bytes([offset + 55 + len(length)]) + length + data


def units(value):
    return format(Decimal(value) / Decimal(10**18), "f")


class Transfer:
    def __init__(self, payload):
        fields = {"chainId", "nonce", "to", "value", "gasLimit",
                  "maxPriorityFeePerGas", "maxFeePerGas"}
        if not isinstance(payload, dict) or set(payload) != fields:
            raise ValueError("Only native ETH transfers are supported; unexpected fields")
        self.data = dict(payload)
        for name in fields - {"to"}:
            value = payload[name]
            # Strings avoid browser precision loss. Strict canonical base-10 input.
            if not isinstance(value, str) or not re.fullmatch(r"0|[1-9][0-9]{0,77}", value):
                raise ValueError(name + " must be an unsigned decimal string")
            self.data[name] = int(value)
            if self.data[name] >= 2**256:
                raise ValueError(name + " exceeds uint256")
        d = self.data
        if d["chainId"] not in CHAINS:
            raise ValueError("Unsupported chain; use Ethereum or Sepolia")
        if not isinstance(d["to"], str) or not re.fullmatch(r"0x[0-9a-fA-F]{40}", d["to"]):
            raise ValueError("Invalid destination address")
        raw = bytes.fromhex(d["to"][2:])
        if raw == bytes(20):
            raise ValueError("Zero destination is not supported")
        checked = checksum_address(raw)
        chars = d["to"][2:]
        if not (chars.islower() or chars.isupper() or chars.isdigit()) and d["to"] != checked:
            raise ValueError("Incorrect address checksum")
        d["to"] = checked
        if d["gasLimit"] != 21000:
            raise ValueError("This prototype only signs 21,000-gas native transfers")
        if d["value"] == 0 or d["maxFeePerGas"] == 0:
            raise ValueError("Amount and maximum fee must be positive")
        # Keep every reviewed value fully legible on the small display.
        if d["value"] > 10**27 or d["maxFeePerGas"] > 10**15 or d["nonce"] >= 2**64:
            raise ValueError("Value, fee or nonce exceeds this prototype's display limits")
        if d["maxPriorityFeePerGas"] > d["maxFeePerGas"]:
            raise ValueError("Priority fee exceeds maximum fee")
        self.unsigned = [d["chainId"], d["nonce"], d["maxPriorityFeePerGas"],
                         d["maxFeePerGas"], d["gasLimit"], raw, d["value"], b"", []]

    def pages(self):
        d = self.data
        return [
            ("Send ETH", [units(d["value"]), CHAINS[d["chainId"]]]),
            ("Full destination", [d["to"][:21], d["to"][21:]]),
            ("Maximum network fee", [units(d["gasLimit"] * d["maxFeePerGas"]) + " ETH"]),
            ("Review total", [units(d["value"] + d["gasLimit"] * d["maxFeePerGas"]) + " ETH",
                              "Nonce " + str(d["nonce"])]),
            ("Sign transaction?", ["Both buttons: sign", "A: back / B: cancel"]),
        ]

    def sign(self, entropy):
        hashed = digest(b"\x02" + rlp(self.unsigned))
        key = SigningKey.from_string(private_key(entropy), curve=SECP256k1, hashfunc=hashlib.sha256)
        signature = key.sign_digest_deterministic(hashed, hashfunc=hashlib.sha256,
                                                  sigencode=util.sigencode_string_canonize)
        candidates = VerifyingKey.from_public_key_recovery_with_digest(
            signature, hashed, curve=SECP256k1, sigdecode=util.sigdecode_string)
        parity = next((i for i, k in enumerate(candidates)
                       if k.to_string() == key.verifying_key.to_string()), None)
        if parity not in (0, 1):
            raise ValueError("Signature recovery failed")
        r, s = util.sigdecode_string(signature, SECP256k1.order)
        raw = b"\x02" + rlp(self.unsigned + [parity, r, s])
        return {"rawTransaction": "0x" + raw.hex(), "transactionHash": "0x" + digest(raw).hex(),
                "address": address(entropy), "chainId": self.data["chainId"]}
