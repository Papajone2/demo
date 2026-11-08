"""Staking display uses real controller review paths, no signing-key export."""
import unittest
from satooshi.rehearsal import Rehearsal


class StakingReviewTests(unittest.TestCase):
    def test_each_action_has_its_own_explicit_title(self):
        for action in ("stake", "unstake", "claim", "withdraw", "vote", "approve"):
            payload = dict(operation=action, amount="1", symbol="SOL",
                           address="11111111111111111111111111111111",
                           fee="0.000005", feeSymbol="SOL", network="solana-mainnet")
            review = Rehearsal(payload)
            self.assertEqual(review.pages()[0][0], action.capitalize() + " amount")
            self.assertEqual(review.pages()[-1][0], "Confirm " + action)

    def test_claim_can_show_zero_without_weakening_transfer_amounts(self):
        payload = dict(operation="claim", amount="0", symbol="ATOM",
                       address="cosmos1" + "q" * 38, fee="0.01",
                       feeSymbol="ATOM", network="cosmos-mainnet")
        Rehearsal(payload)
        for action in ("send", "swap", "stake"):
            with self.assertRaises(ValueError):
                Rehearsal({**payload, "operation": action})

    def test_review_does_not_accept_extra_secret_fields(self):
        payload = dict(operation="stake", amount="1", symbol="SOL",
                       address="11111111111111111111111111111111",
                       fee="0.000005", feeSymbol="SOL", network="solana-mainnet")
        with self.assertRaises(ValueError):
            Rehearsal({**payload, "seed": "not permitted"})
