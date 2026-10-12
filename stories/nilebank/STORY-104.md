# STORY-104: Send money to a beneficiary within my daily limit

**As a** NileBank customer
**I want to** send money to my saved beneficiaries
**So that** I can pay people, while the bank protects me with a daily limit

Interfaces: web UI and REST API · Test user: `amira` (beneficiary "Omar Farouk" is saved; savings balance EGP 100,000.00)

## Acceptance criteria

- **AC1** Given a saved beneficiary, when I send an amount within my limit, then I see a confirmation with a reference and my balance decreases by that amount.
- **AC2** The daily limit for beneficiary transfers is **EGP 50,000.00 in total per day**, not per transfer: after sending EGP 30,000.00, a second transfer of EGP 30,000.00 on the same day must be refused (API: HTTP 409) with a message about the daily limit.
- **AC3** A single transfer above EGP 50,000.00 is refused (API: HTTP 409).
- **AC4** When a transfer is refused because of the limit, no money leaves my account.
