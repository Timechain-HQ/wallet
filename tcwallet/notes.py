"""Stealth notes and signed transfers.

The byte layout matches the node. Amounts are public. The view key is not a
block field. This module does not apply blocks.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from tcwallet.codec import canonical, seal, shake, unseal
from tcwallet.pq import ML_DSA, ML_KEM, decapsulate, encapsulate, generate, sign

MEMO_LIMIT = 256


class NoteError(Exception):
    """A note or a transfer is malformed."""


def _prefixed(blob: bytes) -> bytes:
    return len(blob).to_bytes(4, "big") + blob


@dataclass
class Output:
    value: int
    onetime_pub: bytes
    rho: bytes
    kem_ct: bytes
    cipher: bytes
    mac: bytes

    def commitment(self) -> bytes:
        return shake(
            b"timecoin.note.v1"
            + self.value.to_bytes(16, "big")
            + _prefixed(self.onetime_pub)
            + self.rho
            + _prefixed(self.kem_ct)
            + _prefixed(self.cipher)
            + self.mac
        )

    def parts(self) -> list[tuple[str, int]]:
        return [
            ("value", 8),
            ("onetime pub", len(self.onetime_pub)),
            ("rho", len(self.rho)),
            ("kem ct", len(self.kem_ct)),
            ("cipher", len(self.cipher)),
            ("mac", len(self.mac)),
        ]


def nullifier(onetime_pub: bytes, rho: bytes) -> bytes:
    return shake(b"timecoin.null.v1" + shake(b"pk" + onetime_pub) + rho)


def create_output(view_pub: bytes, value: int, memo: bytes = b"") -> tuple[Output, bytes]:
    if value < 0 or value >= 2**64:
        raise NoteError("value out of range")
    if len(memo) > MEMO_LIMIT:
        raise NoteError("memo too long")
    one_time_private, one_time_public = generate(ML_DSA)
    rho = secrets.token_bytes(32)
    kem_ct, shared = encapsulate(view_pub)
    cipher, mac = seal(shared, _pack(value, rho, one_time_private, memo))
    return Output(value, one_time_public, rho, kem_ct, cipher, mac), one_time_private


def open_output(output: Output, view_private: bytes) -> tuple[bytes, bytes] | None:
    plaintext = unseal(decapsulate(view_private, output.kem_ct), output.cipher, output.mac)
    if plaintext is None:
        return None
    try:
        value, rho, one_time_private, memo = _unpack(plaintext)
    except NoteError:
        return None
    if value != output.value or rho != output.rho:
        return None
    return one_time_private, memo


@dataclass
class Spend:
    output: Output
    signature: bytes

    def to_dict(self, sigs: bool) -> dict[str, object]:
        body = {
            "value": self.output.value,
            "onetime_pub": self.output.onetime_pub.hex(),
            "rho": self.output.rho.hex(),
            "kem_ct": self.output.kem_ct.hex(),
            "cipher": self.output.cipher.hex(),
            "mac": self.output.mac.hex(),
            "signature": self.signature.hex() if sigs else "",
        }
        return body


@dataclass
class Tx:
    inputs: list[Spend]
    outputs: list[Output]
    fee: int

    def to_dict(self, sigs: bool = True) -> dict[str, object]:
        return {
            "kind": "transfer",
            "fee": self.fee,
            "inputs": [spend.to_dict(sigs) for spend in self.inputs],
            "outputs": [
                {
                    "value": output.value,
                    "onetime_pub": output.onetime_pub.hex(),
                    "rho": output.rho.hex(),
                    "kem_ct": output.kem_ct.hex(),
                    "cipher": output.cipher.hex(),
                    "mac": output.mac.hex(),
                }
                for output in self.outputs
            ],
            "deploy": None,
            "call": None,
        }

    def sighash(self) -> bytes:
        return shake(b"timecoin.sighash.v1" + canonical(self.to_dict(sigs=False)))


def transfer(spends: list[tuple[Output, bytes]], outputs: list[Output], fee: int = 0) -> Tx:
    tx = Tx([Spend(output, b"") for output, _private in spends], list(outputs), fee)
    digest = tx.sighash()
    tx.inputs = [Spend(output, sign(private, digest)) for output, private in spends]
    return tx


def _pack(value: int, rho: bytes, one_time_private: bytes, memo: bytes) -> bytes:
    return b"".join(
        [
            b"TN1",
            value.to_bytes(8, "big"),
            rho,
            _prefixed(one_time_private),
            len(memo).to_bytes(2, "big"),
            memo,
        ]
    )


def _unpack(plaintext: bytes) -> tuple[int, bytes, bytes, bytes]:
    if not plaintext.startswith(b"TN1") or len(plaintext) < 3 + 8 + 32 + 4:
        raise NoteError("plaintext")
    cursor = 3
    value = int.from_bytes(plaintext[cursor : cursor + 8], "big")
    cursor += 8
    rho = plaintext[cursor : cursor + 32]
    cursor += 32
    key_len = int.from_bytes(plaintext[cursor : cursor + 4], "big")
    cursor += 4
    if key_len < 0 or cursor + key_len + 2 > len(plaintext):
        raise NoteError("plaintext")
    one_time_private = plaintext[cursor : cursor + key_len]
    cursor += key_len
    memo_len = int.from_bytes(plaintext[cursor : cursor + 2], "big")
    cursor += 2
    if cursor + memo_len != len(plaintext):
        raise NoteError("plaintext")
    return value, rho, one_time_private, plaintext[cursor:]


_KEM_ALGORITHM = ML_KEM
