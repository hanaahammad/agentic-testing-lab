# STORY-102: See my accounts and my total balance

**As a** NileBank customer
**I want to** see all my accounts with their balances and the total
**So that** I know at a glance how much money I have

Interfaces: web UI and REST API · Test user: `amira` (current account EGP 25,000.00 and savings EGP 100,000.00)

## Acceptance criteria

- **AC1** Given I am signed in, when I open my accounts page, then I see every account I own with its type, IBAN and balance (API: `GET /api/accounts`).
- **AC2** Balances are shown as money: `EGP` followed by thousands separators and 2 decimals, e.g. `EGP 25,000.00`.
- **AC3** The "Total balance across all accounts" equals the **sum of all my account balances** (for Amira: `EGP 125,000.00`).
- **AC4** Given I am not signed in, when I open the accounts page, then I am sent to the sign-in page (API: HTTP 401).
