# STORY-101: Sign in securely, with lockout after failed attempts

**As a** NileBank customer
**I want to** sign in with my username and password
**So that** only I can see and move my money

Interfaces: web UI and REST API · Test users: `amira` / `Nile@2026`, `omar` / `Pyramid#77`

## Acceptance criteria

- **AC1** Given valid credentials, when I sign in on the web, then I land on my accounts page and see my name.
- **AC2** Given a wrong password, when I sign in, then I see "Invalid username or password." and stay on the sign-in page (API: HTTP 401).
- **AC3** Given 3 wrong passwords in a row, when I try again, then my account is locked: I see a message telling me it is locked (API: HTTP 423), **even if I now enter the correct password**.
- **AC4** Given an unknown username, when I sign in, then I see the same generic error as for a wrong password (no hint that the user does not exist).
