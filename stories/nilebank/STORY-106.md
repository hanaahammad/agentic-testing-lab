# STORY-106: Browse my transaction history

**As a** NileBank customer
**I want to** browse the transactions of each account
**So that** I can check every payment

Interfaces: web UI and REST API · Test user: `amira` (current account CUR-1001 has 25 past transactions)

## Acceptance criteria

- **AC1** Transactions are listed newest first, 10 per page, with date, description and amount.
- **AC2** Paging through the history shows **every transaction exactly once**: no transaction is repeated on two pages and none is skipped (API: `GET /api/accounts/{id}/transactions?page=n`).
- **AC3** The page indicator shows the current page, the number of pages and the number of transactions (25 transactions → 3 pages).
- **AC4** Given an account that is not mine, when I open its history, then I get an error (API: HTTP 404) and see no data.
