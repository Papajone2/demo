"""Public zero-entropy interoperability fixtures, never real wallet material."""
import hashlib
import unittest
from ecdsa import SECP256k1, VerifyingKey, util
from satooshi.signing import SECP_PATHS, _seed, sign
from satooshi.receive import receive_address
from embit import bip32, bech32


class CosmosTests(unittest.TestCase):
    def test_one_bip39_phrase_fixed_path_and_chain_specific_receive_addresses(self):
        entropy = bytes(32)
        public = bip32.HDKey.from_seed(_seed(entropy)).derive("m/44h/118h/0h/0/0").key.get_public_key().sec()
        digest = hashlib.sha256(b"unfunded Cosmos SignDoc test").digest()
        for kind in ("cosmos", "celestia", "akash", "fetch"):
            self.assertEqual(SECP_PATHS[kind], "m/44h/118h/0h/0/0")
            address = receive_address(entropy, kind)
            encoding, prefix, words = bech32.bech32_decode(address)
            self.assertEqual(encoding, bech32.Encoding.BECH32)
            self.assertEqual(prefix, kind)
            body = bytes(bech32.convertbits(words, 5, 8, False))
            self.assertEqual(body, hashlib.new("ripemd160", hashlib.sha256(public).digest()).digest())
            signature = bytes.fromhex(sign(entropy, kind, digest)["signature"])
            self.assertTrue(VerifyingKey.from_string(public, curve=SECP256k1).verify_digest(signature, digest, sigdecode=util.sigdecode_string))

    def test_wrong_digest_length_cannot_sign(self):
        for kind in ("cosmos", "celestia", "akash", "fetch"):
            with self.assertRaises(ValueError):
                sign(bytes(32), kind, b"not a transaction digest")
