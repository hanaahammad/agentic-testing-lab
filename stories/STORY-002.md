# STORY-002: Deposit and withdraw money

**As a** bank customer
**I want to** deposit and withdraw money
**So that** my balance always reflects what I own

## Acceptance criteria

- **AC1** Given an account, when I deposit a positive amount, then I get HTTP 200 and the balance increases by exactly that amount.
- **AC2** Given an account, when I deposit zero or a negative amount, then I get HTTP 422 and the balance is unchanged.
- **AC3** Given an account, when I withdraw a positive amount not exceeding the balance, then I get HTTP 200 and the balance decreases by that amount.
- **AC4** Given an account, when I withdraw more than the balance, then I get HTTP 409 and the balance is unchanged.
- **AC5** Balances are money: they are always rounded to 2 decimals (for example, depositing 0.10 then 0.20 gives a balance of exactly 0.30).
