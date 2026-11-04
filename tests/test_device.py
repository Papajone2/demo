"""Public deterministic test fixtures only. Never use these keys for funds."""
import copy
import json
import os
import tempfile
import textwrap
import unittest

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils
from ecdsa import SECP256k1, SigningKey, util
from satooshi.controller import Controller
from satooshi.evm import Transfer, WORDLIST, address, digest, private_key, rlp
from satooshi.protocol import Protocol
from satooshi.vault import Vault, WrongPIN

ENTROPY = bytes(32)  # Public BIP39 "abandon ... art" vector. NOT a funded wallet.
ADDRESS = "0xF278cF59F82eDcf871d630F28EcC8056f25C1cdb"
PAYLOAD = dict(chainId="11155111", nonce="0", to="0x1111111111111111111111111111111111111111",
               value="1000000000000000", gasLimit="21000",
               maxPriorityFeePerGas="1000000000", maxFeePerGas="3000000000")
RAW = "0x02f87483aa36a780843b9aca0084b2d05e0082520894111111111111111111111111111111111111111187038d7ea4c6800080c080a0d73b7d734fd8cd95582e580a9e417249fb38b40da89a51ee4db69eef0d912e2ca02374d3c8731434686aa7729b799bb55f27bb0690fcefb548d18f1b651c7d4c0f"


class CryptoTests(unittest.TestCase):
    def test_bip39_vector(self):
        words = WORDLIST.to_mnemonic(ENTROPY)
        self.assertEqual(words, " ".join(["abandon"] * 23 + ["art"]))
        self.assertTrue(WORDLIST.check(words))
        self.assertEqual(address(ENTROPY), ADDRESS)

    def test_rlp_vectors(self):
        self.assertEqual(rlp(b"dog").hex(), "83646f67")
        self.assertEqual(rlp([b"cat", b"dog"]).hex(), "c88363617483646f67")
        self.assertEqual(rlp(0), b"\x80")

    def test_deterministic_signed_transaction(self):
        signed = Transfer(PAYLOAD).sign(ENTROPY)
        self.assertEqual(signed["rawTransaction"], RAW)
        self.assertEqual(signed["transactionHash"], "0xffa4955c0ebfc05dbf601618fcc91039e3b34e62a20d18c15a166572e389b3e4")

    def test_signature_independent_openssl_verification(self):
        transfer = Transfer(PAYLOAD)
        hashed = digest(b"\x02" + rlp(transfer.unsigned))
        key = SigningKey.from_string(private_key(ENTROPY), curve=SECP256k1)
        import hashlib
        sig = key.sign_digest_deterministic(hashed, hashfunc=hashlib.sha256,
                                            sigencode=util.sigencode_string_canonize)
        r, s = util.sigdecode_string(sig, SECP256k1.order)
        self.assertLessEqual(s, SECP256k1.order // 2)
        public = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256K1(),
                                                            b"\x04" + key.verifying_key.to_string())
        public.verify(utils.encode_dss_signature(r, s), hashed, ec.ECDSA(utils.Prehashed(hashes.SHA256())))

    def test_reject_unsupported_and_ambiguous_payloads(self):
        variants = [
            dict(data="0xa9059cbb"), dict(chainId="56"), dict(chainId=1),
            dict(nonce="-1"), dict(nonce="01"), dict(nonce="1e2"),
            dict(value="0"), dict(value=str(2**256)), dict(gasLimit="22000"),
            dict(to="0x" + "0" * 40), dict(maxPriorityFeePerGas="9000000000"),
            dict(to="hello.eth"), dict(to=ADDRESS.replace("F278", "f278")),
            dict(maxFeePerGas="0"), dict(nonce=str(2**64)),
        ]
        for variant in variants:
            with self.subTest(variant=variant), self.assertRaises(ValueError):
                Transfer({**PAYLOAD, **variant})

    def test_review_snapshot_not_mutable_by_host(self):
        data = copy.deepcopy(PAYLOAD)
        transfer = Transfer(data)
        data["to"] = "0x" + "2" * 40
        self.assertEqual(transfer.data["to"], PAYLOAD["to"])

    def test_full_amount_and_destination_on_display(self):
        tx = Transfer(PAYLOAD)
        self.assertEqual("".join(tx.pages()[1][1]), PAYLOAD["to"])
        tx = Transfer({**PAYLOAD, "value": str(10**27), "maxFeePerGas": str(10**15),
                       "nonce": str(2**64 - 1)})
        for title, lines in tx.pages():
            wrapped = sum((textwrap.wrap(line, 21, break_on_hyphens=False) for line in lines), [])
            self.assertLessEqual(len(wrapped), 4, title)


class DeviceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.vault = Vault(self.tmp.name)
        self.events = []
        self.now = 100.0
        self.device = Controller(self.vault, self.events.append, clock=lambda: self.now)

    def tearDown(self):
        self.tmp.cleanup()

    def configured(self, pin="1234"):
        self.vault.create(ENTROPY, pin)
        self.device.entropy = self.vault.unlock(pin)

    def enter_pin(self, pin):
        for digit in pin:
            target = int(digit)
            while self.device.digit != target:
                self.device.button("b")
            self.device.button("both")
        while self.device.digit != 10:
            self.device.button("b")
        self.device.button("both")

    def test_vault_is_encrypted_and_permissions_private(self):
        self.vault.create(ENTROPY, "1234")
        raw = self.vault.path.read_bytes()
        self.assertNotIn(WORDLIST.to_mnemonic(ENTROPY).encode(), raw)
        self.assertNotIn(b"1234", raw)
        self.assertEqual(self.vault.unlock("1234"), ENTROPY)
        self.assertEqual(os.stat(self.vault.path).st_mode & 0o777, 0o600)

    def test_pinless_device_key_is_separate_and_stable(self):
        self.vault.create(ENTROPY, None)
        self.assertTrue(self.vault.key_path.exists())
        self.assertEqual(Vault(self.tmp.name).unlock(), ENTROPY)

    def test_five_attempts_persist_and_wipe(self):
        self.vault.create(ENTROPY, "1234")
        for i in range(5):
            vault = Vault(self.tmp.name)
            with self.assertRaises(WrongPIN) as result:
                vault.unlock("5555")
            self.assertEqual(result.exception.remaining, 4 - i)
        self.assertFalse(self.vault.exists)
        self.assertFalse(self.vault.key_path.exists())

    def test_success_resets_failed_counter(self):
        self.vault.create(ENTROPY, "1234")
        with self.assertRaises(WrongPIN):
            self.vault.unlock("8888")
        self.vault.unlock("1234")
        self.assertEqual(self.vault.metadata()["failed"], 0)

    def test_power_cut_during_final_charged_attempt_does_not_grant_more_tries(self):
        self.vault.create(ENTROPY, "1234")
        data = self.vault.metadata()
        data["failed"] = 5
        self.vault.atomic_write(self.vault.path, json.dumps(data).encode())
        restarted = Vault(self.tmp.name)
        self.assertFalse(restarted.exists)

    def test_existing_wallet_cannot_be_replaced_by_setup(self):
        self.configured()
        with self.assertRaises(ValueError):
            self.device.request("setup", {}, "setup")
        self.assertEqual(self.vault.unlock("1234"), ENTROPY)

    def test_setup_requires_physical_backup_and_pin_confirmation(self):
        self.device.request("setup", {}, "setup")
        self.assertIsNone(self.device.entropy)
        self.device.button("both")
        self.device.button("both")  # Cannot skip the words.
        self.assertEqual(self.device.phase, "backup")
        for _ in range(23):
            self.device.button("b")
        self.device.button("both")
        for _ in range(3):
            correct = self.device._words()[self.device.quiz_positions[self.device.quiz_index]]
            while self.device.quiz[self.device.choice] != correct:
                self.device.button("b")
            self.device.button("both")
        self.device.button("both")  # Choose PIN.
        self.enter_pin("1234")
        self.assertFalse(self.vault.exists)
        self.enter_pin("1234")
        self.assertTrue(self.vault.exists)
        self.assertEqual(self.device.phase, "home")
        self.assertEqual(len(WORDLIST.to_mnemonic(self.vault.unlock("1234")).split()), 24)

    def test_cancelled_unsaved_seed_cannot_sign(self):
        self.device.request("setup", {}, "s")
        self.device.button("both")
        self.device.cancel()
        self.assertIsNone(self.device.entropy)
        with self.assertRaises(ValueError):
            self.device.request("review_transfer", PAYLOAD, "sign")

    def test_receive_address_requires_button_confirmation(self):
        self.configured()
        result = self.device.request("get_address", {}, "address")
        self.assertEqual(result, {"accepted": True})
        self.assertFalse(any(e["event"] == "result" for e in self.events))
        self.device.button("both")
        self.assertEqual(self.events[-2]["data"]["result"]["address"], ADDRESS)

    def test_signing_requires_every_review_page(self):
        self.configured()
        self.device.request("review_transfer", PAYLOAD, "sign")
        self.device.button("both")
        self.assertFalse(any(e["event"] == "result" for e in self.events))
        for _ in range(4):
            self.device.button("b")
        self.device.button("both")
        result = next(e for e in self.events if e["event"] == "result")
        self.assertEqual(result["data"]["result"]["rawTransaction"], RAW)
        self.assertEqual(self.device.phase, "home")

    def test_no_remote_buttons_seed_or_arbitrary_signing(self):
        self.configured()
        for method in ("button", "get_seed", "export_seed", "set_pin", "sign_hash", "exec"):
            with self.assertRaises(ValueError):
                self.device.request(method, {}, method)

    def test_usb_state_never_contains_secret_screen_or_pin(self):
        self.device.request("setup", {}, "s")
        self.device.button("both")
        words = WORDLIST.to_mnemonic(self.device.entropy)
        self.assertNotIn(words, json.dumps(self.events))
        self.assertNotIn(self.device.display()[1][0], json.dumps(self.events))
        self.assertNotIn("entropy", json.dumps(self.events))
        self.assertNotIn("privateKey", json.dumps(self.events))

    def test_reconnect_unlock_reuses_identity(self):
        self.configured()
        second = Controller(Vault(self.tmp.name), self.events.append)
        self.assertTrue(second.status()["locked"])
        second.request("unlock", {}, "unlock")
        second.button("both")
        self.device = second
        self.enter_pin("1234")
        self.assertEqual(address(second.entropy), ADDRESS)

    def test_physical_reset_requires_two_confirmations(self):
        self.configured()
        self.device.request("reset", {}, "r")
        self.device.button("both")
        self.assertTrue(self.vault.exists)
        self.device.button("both")
        self.assertFalse(self.vault.exists)
        self.assertIsNone(self.device.entropy)

    def test_idle_and_disconnected_auto_lock(self):
        self.configured()
        self.now += 46
        self.device.tick()
        self.assertIsNone(self.device.entropy)

    def test_protocol_envelopes_replays_and_bounds(self):
        proto = Protocol(self.device)
        request = json.dumps(dict(v=1, id="hello-1", method="hello", params={}))
        self.assertTrue(proto.handle(request)["ok"])
        self.assertFalse(proto.handle(request)["ok"])
        for value in ("{", "[]", "{}",
                      json.dumps(dict(v=2, id="wrong", method="hello")),
                      json.dumps(dict(v=1, id="params", method="hello", params=[])),
                      "x" * 4097):
            self.assertFalse(proto.handle(value)["ok"])


if __name__ == "__main__":
    unittest.main()
