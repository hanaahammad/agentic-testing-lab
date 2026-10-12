# STORY-107: Sign out and end my session

**As a** NileBank customer
**I want to** sign out
**So that** nobody can use my session after I leave, for example on a shared computer

Interfaces: web UI and REST API · Test user: `amira`

## Acceptance criteria

- **AC1** Given I am signed in on the web, when I click "Sign out", then I am back on the sign-in page with a message that I signed out.
- **AC2** After signing out on the web, opening the accounts page sends me back to sign in.
- **AC3** After `POST /api/auth/logout`, the same session token is **rejected** by every API call (HTTP 401): the session is ended on the server, not just forgotten by the browser.
