# STORY-003: Transfer money between accounts

**As a** bank customer
**I want to** transfer money from one of my accounts to another account
**So that** I can pay people

## Acceptance criteria

- **AC1** Given two accounts and a positive amount not exceeding the source balance, when I transfer, then I get HTTP 201 with a transfer `id` starting with `TRF-` and `status` = `completed`; the source decreases and the destination increases by the amount.
- **AC2** Given a transfer amount larger than the source balance, when I transfer, then I get HTTP 409 and **both balances are unchanged** (no overdraft).
- **AC3** Given the same account as source and destination, when I transfer, then I get HTTP 422.
- **AC4** Given a source or destination account that does not exist, when I transfer, then I get HTTP 404.
- **AC5** Given a zero or negative amount, when I transfer, then I get HTTP 422.
