# Timecoin wallet

Testnet wallet behavior for Timecoin. This is not a mainnet wallet and it does not talk to a public network.

The node and the demo client live in [Timecoin](https://github.com/Timechain-HQ/Timecoin). Protocol details are in the [book](https://github.com/Timechain-HQ/book).

## Keys

Each wallet has two local keys:

- An ML-KEM-768 view key. It opens notes sent to this wallet.
- An ML-DSA-44 capability key. It authorizes contract deployment and contract calls.

Spend keys are one-time. The sender generates one for each new note and encrypts it to the recipient's view key.

## Scan

The wallet reads every unspent note. It decapsulates the ML-KEM ciphertext with the view key and checks the MAC. A note that fails the MAC is ignored. A note that opens yields the one-time spend key, the memo, and the amount.

## Pay

The wallet selects its own notes until they cover the amount and the fee. It builds one note for the recipient and, when needed, a change note for itself. Each input is signed by its one-time key.

## Sweep

Sweep spends a received note into a new note addressed to the same wallet. After the sweep is in a block, the sender's view key cannot open the new note. If the sender kept the original one-time key, that key is useless once the nullifier is published.

## What remains visible

Amounts, fees, and which note was spent are on the chain. The view key and the memo are not.
