"""Note opening, conservation, and the sweep."""

from __future__ import annotations

import unittest

from tcwallet.ledger import Ledger, LedgerError, Wallet
from tcwallet.notes import create_output, open_output, transfer

BASE = 10**8


class WalletTests(unittest.TestCase):
    def test_pay_sweep_and_rejected_inflation(self) -> None:
        alice = Wallet.create("alice")
        bob = Wallet.create("bob")
        carol = Wallet.create("carol")
        ledger = Ledger()
        funded, _key = create_output(alice.view_pub, 50 * BASE, b"fund")
        ledger.add(funded)
        self.assertEqual(len(alice.scan(ledger)), 1)
        self.assertEqual(carol.scan(ledger), [])

        payment = alice.pay(ledger, bob.view_pub, 20 * BASE, b"for bob", fee=500)
        self.assertEqual(sum(output.value for output in payment.outputs) + payment.fee, 50 * BASE)
        ledger.apply(payment)
        opened = bob.scan(ledger)
        self.assertEqual(opened[0][2], b"for bob")
        self.assertEqual(alice.balance(ledger) + bob.balance(ledger), 50 * BASE - 500)

        sweep = bob.pay(ledger, bob.view_pub, bob.balance(ledger), b"sweep")
        ledger.apply(sweep)
        for output, _key, _memo in bob.scan(ledger):
            self.assertIsNone(open_output(output, alice.view_private))

        note, spend_key, _memo = alice.scan(ledger)[0]
        broken = transfer(
            [(note, spend_key)],
            [create_output(bob.view_pub, note.value + 1, b"no")[0]],
        )
        with self.assertRaises(LedgerError):
            ledger.apply(broken)
        self.assertEqual(alice.balance(ledger), note.value)
