# STORY-103: Transfer between my own accounts

**As a** NileBank customer
**I want to** move money between my own accounts
**So that** I can save or spend as I need

Interfaces: web UI and REST API · Test user: `amira`

## Acceptance criteria

- **AC1** Given enough money in the source account, when I transfer an amount to another of my accounts, then I see a confirmation with a reference, the source balance decreases and the destination balance increases by exactly that amount.
- **AC2** Given an amount larger than the source balance, when I transfer, then I see "Insufficient funds" (API: HTTP 409) and no balance changes.
- **AC3** Given an amount of zero or a negative amount, when I transfer, then the transfer is refused (API: HTTP 422).
- **AC4** Given the same account as source and destination, when I transfer, then the transfer is refused (API: HTTP 422).
