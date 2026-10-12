# STORY-105: Manage beneficiaries safely

**As a** NileBank customer
**I want to** add people I send money to as beneficiaries
**So that** I do not retype their IBAN every time

Interfaces: web UI and REST API · Test user: `amira`

## Acceptance criteria

- **AC1** Given a nickname and a valid Egyptian IBAN (`EG` followed by exactly 27 digits, spaces allowed when typing), when I add a beneficiary, then I see a confirmation and the beneficiary appears in my list (API: HTTP 201).
- **AC2** Given an IBAN that is not `EG` + 27 digits (too short, too long, letters, other country), when I add it, then it is refused with a clear message (API: HTTP 422) and nothing is added.
- **AC3** Given an empty nickname, when I add a beneficiary, then it is refused (API: HTTP 422).
- **AC4** Nicknames are shown **exactly as typed**: text such as `<b>Laila</b>` or `<img src=x onerror=alert(1)>` must appear as plain text in the list, never be interpreted as HTML or script.
