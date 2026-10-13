"""Charts from one wallet session: fund, pay, sweep."""

from __future__ import annotations

from pathlib import Path

from tcwallet.ledger import Ledger, Wallet
from tcwallet.notes import create_output
from tcwallet.pngchart import composition_chart, line_chart, bar_chart

BASE = 10**8
FEE = 500


def write_charts(directory: str | Path) -> dict[str, object]:
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    session = run_session()
    steps = [row[0] for row in session["rows"]]
    line_chart(
        path / "balances.png",
        "Balances through fund, pay, and sweep",
        "step",
        "TIC",
        [
            ("alice", list(zip(steps, session["alice"]))),
            ("bob", list(zip(steps, session["bob"]))),
        ],
    )
    line_chart(
        path / "opened.png",
        "Notes on the set versus notes each view key opens",
        "step",
        "count",
        [
            ("set", list(zip(steps, session["notes"]))),
            ("alice", list(zip(steps, session["alice_open"]))),
            ("bob", list(zip(steps, session["bob_open"]))),
        ],
    )
    composition_chart(path / "note-bytes.png", "Measured bytes in the funded note", session["parts"])
    bar_chart(
        path / "selection.png",
        "Inputs spent and change notes created",
        "payment",
        ["pay", "sweep"],
        [
            ("inputs", [float(session["pay_inputs"]), float(session["sweep_inputs"])]),
            ("change", [float(session["pay_change"]), float(session["sweep_change"])]),
        ],
    )
    report = _report(session)
    (path / "README.md").write_text(report, encoding="utf-8")
    return session


def run_session() -> dict[str, object]:
    alice = Wallet.create("alice")
    bob = Wallet.create("bob")
    carol = Wallet.create("carol")
    ledger = Ledger()
    funded, _key = create_output(alice.view_pub, 50 * BASE, b"fund")
    rows: list[tuple[int, int, int, int, int, int]] = []

    def snap(step: int) -> None:
        rows.append(
            (
                step,
                alice.balance(ledger),
                bob.balance(ledger),
                len(ledger.notes),
                len(alice.scan(ledger)),
                len(bob.scan(ledger)),
            )
        )

    snap(0)
    ledger.add(funded)
    snap(1)
    payment = alice.pay(ledger, bob.view_pub, 20 * BASE, b"for bob", FEE)
    pay_inputs = len(payment.inputs)
    pay_change = sum(1 for output in payment.outputs if open_output_safe(output, alice))
    ledger.apply(payment)
    snap(2)
    sweep = bob.pay(ledger, bob.view_pub, bob.balance(ledger), b"sweep")
    sweep_inputs = len(sweep.inputs)
    sweep_change = sum(1 for output in sweep.outputs if open_output_safe(output, bob) and output.value != bob.balance(ledger))
    # Sweep spends the whole balance, so the new note is the payment, not change.
    sweep_change = len(sweep.outputs) - 1
    ledger.apply(sweep)
    snap(3)
    swept = bob.scan(ledger)
    hidden = all(open_output_safe(output, alice) is None for output, _k, _m in swept)
    stranger = carol.balance(ledger) == 0 and all(
        open_output_safe(output, carol) is None for output in ledger.notes.values()
    )
    return {
        "rows": rows,
        "alice": [row[1] / BASE for row in rows],
        "bob": [row[2] / BASE for row in rows],
        "notes": [float(row[3]) for row in rows],
        "alice_open": [float(row[4]) for row in rows],
        "bob_open": [float(row[5]) for row in rows],
        "parts": funded.parts(),
        "pay_inputs": pay_inputs,
        "pay_change": pay_change,
        "sweep_inputs": sweep_inputs,
        "sweep_change": sweep_change,
        "hidden_from_sender": hidden,
        "stranger_blind": stranger,
        "bob_final": bob.balance(ledger),
        "alice_final": alice.balance(ledger),
        "fee": FEE,
    }


def open_output_safe(output, wallet: Wallet):
    from tcwallet.notes import open_output

    return open_output(output, wallet.view_private)


def _report(session: dict[str, object]) -> str:
    lines = [
        "# Measured wallet charts",
        "",
        "Written by `python3 -m tcwallet.cli charts`.",
        "",
        "| Step | Alice TIC | Bob TIC | Notes | Alice opens | Bob opens |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row, alice, bob in zip(session["rows"], session["alice"], session["bob"]):
        lines.append(
            f"| {row[0]} | {alice:g} | {bob:g} | {row[3]} | {row[4]} | {row[5]} |"
        )
    lines.extend(
        [
            "",
            f"Payment fee: {session['fee']} base units.",
            f"Alice final: {session['alice_final']} base units. Bob final: {session['bob_final']} base units.",
            f"Sender can open Bob's swept note: {not session['hidden_from_sender']}.",
            f"A third view key opens nothing: {session['stranger_blind']}.",
            "",
        ]
    )
    return "\n".join(lines)
