# STORY-001: Open an account and check its balance

**As a** bank customer
**I want to** open an account with an optional opening deposit and look it up later
**So that** I can start banking with MiniBank

## Acceptance criteria

- **AC1** Given a non-empty owner name and an initial deposit ≥ 0, when I open an account, then I get HTTP 201 with an `id` starting with `ACC-`, the `owner`, and a `balance` equal to the initial deposit.
- **AC2** Given an existing account, when I look it up by id, then I get HTTP 200 and its current `balance`.
- **AC3** Given an empty or blank owner name, when I open an account, then I get HTTP 422.
- **AC4** Given a negative initial deposit, when I open an account, then I get HTTP 422.
- **AC5** Given an account id that does not exist, when I look it up, then I get HTTP 404.
