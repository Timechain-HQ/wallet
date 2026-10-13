"""Local note set used before a transaction is submitted.

The node re-checks every rule. This ledger refuses a transfer that does not
conserve TIC or whose one-time key does not sign the sighash.
"""

from __future__ import annotations

from tcwallet.notes import NoteError, Output, Tx, nullifier, open_output
from tcwallet.pq import ML_DSA, ML_KEM, generate, verify


class LedgerError(Exception):
    """The local note set rejected a transfer."""


class Ledger:
    def __init__(self) -> None:
        self.notes: dict[bytes, Output] = {}
        self.nullifiers: set[bytes] = set()

    def add(self, output: Output) -> None:
        commitment = output.commitment()
        if commitment in self.notes or len(output.rho) != 32:
            raise LedgerError("note")
        self.notes[commitment] = output

    def apply(self, tx: Tx) -> None:
        if tx.fee < 0 or not tx.inputs:
            raise LedgerError("shape")
        digest = tx.sighash()
        incoming = 0
        removing: list[bytes] = []
        markers: list[bytes] = []
        for spend in tx.inputs:
            output = spend.output
            commitment = output.commitment()
            if self.notes.get(commitment) != output:
                raise LedgerError("unknown note")
            marker = nullifier(output.onetime_pub, output.rho)
            if marker in self.nullifiers or marker in markers:
                raise LedgerError("double spend")
            if not verify(output.onetime_pub, digest, spend.signature):
                raise LedgerError("note signature")
            incoming += output.value
            removing.append(commitment)
            markers.append(marker)
        outgoing = tx.fee
        fresh: list[Output] = []
        seen: set[bytes] = set()
        for output in tx.outputs:
            if output.value < 0 or len(output.rho) != 32:
                raise LedgerError("value")
            outgoing += output.value
            commitment = output.commitment()
            if commitment in self.notes or commitment in seen:
                raise LedgerError("note")
            seen.add(commitment)
            fresh.append(output)
        if incoming != outgoing:
            raise LedgerError("conservation")
        for commitment, marker in zip(removing, markers):
            del self.notes[commitment]
            self.nullifiers.add(marker)
        for output in fresh:
            self.notes[output.commitment()] = output


class Wallet:
    def __init__(self, name: str, view_private: bytes, view_pub: bytes, cap_private: bytes, cap_pub: bytes) -> None:
        self.name = name
        self.view_private = view_private
        self.view_pub = view_pub
        self.cap_private = cap_private
        self.cap_pub = cap_pub

    @classmethod
    def create(cls, name: str) -> Wallet:
        view_private, view_pub = generate(ML_KEM)
        cap_private, cap_pub = generate(ML_DSA)
        return cls(name, view_private, view_pub, cap_private, cap_pub)

    def scan(self, ledger: Ledger) -> list[tuple[Output, bytes, bytes]]:
        found: list[tuple[Output, bytes, bytes]] = []
        for output in ledger.notes.values():
            opened = open_output(output, self.view_private)
            if opened is None:
                continue
            spend_key, memo = opened
            found.append((output, spend_key, memo))
        return found

    def balance(self, ledger: Ledger) -> int:
        return sum(output.value for output, _key, _memo in self.scan(ledger))

    def pay(self, ledger: Ledger, recipient_view_pub: bytes, amount: int, memo: bytes = b"", fee: int = 0) -> Tx:
        from tcwallet.notes import create_output, transfer

        if amount <= 0 or fee < 0:
            raise NoteError("amount")
        selected: list[tuple[Output, bytes]] = []
        total = 0
        for output, spend_key, _memo in self.scan(ledger):
            selected.append((output, spend_key))
            total += output.value
            if total >= amount + fee:
                break
        if total < amount + fee:
            raise NoteError("insufficient TIC")
        outputs = [create_output(recipient_view_pub, amount, memo)[0]]
        change = total - amount - fee
        if change:
            outputs.append(create_output(self.view_pub, change, b"change")[0])
        return transfer(selected, outputs, fee)
