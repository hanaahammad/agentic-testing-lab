"""Demo-mode knowledge for NileBank: the test cases and scripts the scripted brain 'writes'.

The scripts live in agent/demo_scripts/nilebank/. STORY-104's first script contains a deliberate test bug
(it clicks a button id that does not exist) so you can watch the agent repair its own UI test.
"""
import json
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent / "demo_scripts" / "nilebank"


def c(tc, title, kind, crit, iface, steps, expected):
    return {"id": tc, "title": title, "type": kind, "criterion": crit, "interface": iface,
            "steps": steps, "expected": expected}


CASES = {
    "STORY-101": [
        c("TC-101-01", "Valid sign-in lands on accounts page", "positive", "AC1", "UI",
          ["Open /login", "Enter amira / Nile@2026", "Click Sign in"], "Accounts page, name 'Amira Hassan' shown"),
        c("TC-101-02", "Wrong password shows generic error", "negative", "AC2", "UI",
          ["Open /login", "Enter amira / wrong password", "Click Sign in"], "'Invalid username or password.', stays on /login"),
        c("TC-101-03", "Account locks after 3 failed attempts", "negative", "AC3", "API",
          ["POST /api/auth/login with wrong password ×3", "POST /api/auth/login with correct password"], "HTTP 423 locked"),
        c("TC-101-04", "Unknown user gets the same error as wrong password", "negative", "AC4", "API",
          ["Login as unknown user", "Login as omar with wrong password"], "Both 401 with identical message"),
    ],
    "STORY-102": [
        c("TC-102-01", "API lists all my accounts with balances", "positive", "AC1", "API",
          ["Sign in as amira", "GET /api/accounts"], "CUR-1001 25,000.00 and SAV-1002 100,000.00 with IBANs"),
        c("TC-102-02", "Balances formatted as money", "positive", "AC2", "UI",
          ["Sign in", "Read balance on each account card"], "'EGP 25,000.00' and 'EGP 100,000.00'"),
        c("TC-102-03", "Total equals the sum of all accounts", "positive", "AC3", "UI",
          ["Sign in", "Read total balance and each account balance"], "Total = EGP 125,000.00 = sum of cards"),
        c("TC-102-04", "Signed-out users are sent to sign-in", "negative", "AC4", "API + UI",
          ["GET /api/accounts without token", "Open /dashboard without signing in"], "401, redirect to /login"),
    ],
    "STORY-103": [
        c("TC-103-01", "Own transfer moves money", "positive", "AC1", "UI",
          ["Sign in", "Transfer 2,500.75 from CUR-1001 to SAV-1002"],
          "Confirmation with reference; CUR-1001 22,499.25, SAV-1002 102,500.75"),
        c("TC-103-02", "Insufficient funds refused", "negative", "AC2", "API",
          ["Transfer 30,000 from CUR-1001 (balance 25,000)"], "409 'Insufficient funds', balances unchanged"),
        c("TC-103-03", "Zero and negative amounts refused", "boundary", "AC3", "API",
          ["Transfer 0", "Transfer -50"], "422 for both"),
        c("TC-103-04", "Same source and destination refused", "negative", "AC4", "API",
          ["Transfer from CUR-1001 to CUR-1001"], "422"),
    ],
    "STORY-104": [
        c("TC-104-01", "Beneficiary transfer succeeds", "positive", "AC1", "UI",
          ["Sign in", "Send 1,500.00 from SAV-1002 to Omar Farouk"], "Confirmation; SAV-1002 = 98,500.00"),
        c("TC-104-02", "Daily limit is cumulative", "negative", "AC2", "API",
          ["Send 30,000 to Omar", "Send another 30,000 the same day"], "First 201, second 409 (daily limit)"),
        c("TC-104-03", "Single transfer above the limit refused", "boundary", "AC3", "API",
          ["Send 50,000.01 to Omar"], "409, balance unchanged"),
        c("TC-104-04", "Limit message shown and no money moves", "negative", "AC2, AC4", "UI",
          ["Sign in", "Send 30,000 to Omar twice"], "Error mentions daily limit; SAV-1002 = 70,000.00"),
    ],
    "STORY-105": [
        c("TC-105-01", "Add a valid beneficiary (IBAN with spaces)", "positive", "AC1", "UI",
          ["Sign in", "Add 'Laila Mostafa' with a spaced valid IBAN"], "Confirmation; shown once in the list"),
        c("TC-105-02", "Invalid IBANs refused", "negative", "AC2", "API",
          ["Add IBANs: too short, too long, with a letter, German"], "422 for each; still 1 beneficiary"),
        c("TC-105-03", "Empty nickname refused", "negative", "AC3", "API",
          ["Add a beneficiary with a blank nickname"], "422"),
        c("TC-105-04", "Nickname shown as plain text (no HTML / script)", "security", "AC4", "UI",
          ["Sign in", "Add nickname '<b>Laila</b> <img src=x onerror=…>'"], "Shown literally; no markup, no script run"),
    ],
    "STORY-106": [
        c("TC-106-01", "First page has 10 newest-first transactions", "positive", "AC1", "API",
          ["GET history page 1 for CUR-1001"], "10 items sorted by date descending"),
        c("TC-106-02", "Every transaction appears exactly once across pages", "negative", "AC2", "API",
          ["Read all pages of CUR-1001", "Collect ids"], "25 unique ids, no repeats"),
        c("TC-106-03", "Page indicator and paging on screen", "positive", "AC3", "UI",
          ["Sign in", "Open History", "Click Older"], "'Page 1 of 3 · 25 transactions', 10 rows, then page 2"),
        c("TC-106-04", "Another customer's account is hidden", "security", "AC4", "API",
          ["As amira, GET history of omar's CUR-2001"], "404"),
    ],
    "STORY-107": [
        c("TC-107-01", "Sign out shows confirmation", "positive", "AC1", "UI",
          ["Sign in", "Click Sign out"], "Sign-in page with 'signed out' message"),
        c("TC-107-02", "Accounts page needs sign-in again", "positive", "AC2", "UI",
          ["Sign in", "Sign out", "Open /dashboard"], "Redirected to /login"),
        c("TC-107-03", "Session token rejected after logout", "security", "AC3", "API",
          ["Sign in via API", "POST /api/auth/logout", "GET /api/accounts with same token"], "401"),
    ],
}


def script(story_id: str) -> str:
    return (SCRIPTS_DIR / f"test_{story_id.lower().replace('-', '_')}.py").read_text(encoding="utf-8")


def repaired(story_id: str, code: str) -> str:
    # The agent's diagnosis: TC-104-01 clicks data-testid="transfer-send", which does not exist on /transfer;
    # the discovered screen map shows the button is data-testid="transfer-submit".
    return code.replace('get_by_test_id("transfer-send")', 'get_by_test_id("transfer-submit")')


# ---------------------------------------------------------------- scripted exploratory sessions
def _el(out, test_id, field="text"):
    return next((e.get(field, "") for e in out.get("elements", []) if e["id"] == test_id), None)


def _money(text):
    import re

    m = re.search(r"-?[\d,]+\.\d{2}", text or "")
    return float(m.group(0).replace(",", "")) if m else None


def _store_token(out, ctx):
    ctx["token"] = (out.get("body") or {}).get("token")


def _auth(ctx):
    return {"Authorization": f"Bearer {ctx.get('token')}"}


def _sign_in_steps(user="amira", pw="Nile@2026", thought="Signing in through the real sign-in screen."):
    return [
        (thought, "browser_open", {"path": "/login"}, None),
        (None, "browser_fill", {"test_id": "login-username", "text": user}, None),
        (None, "browser_fill", {"test_id": "login-password", "text": pw}, None),
        (None, "browser_click", {"test_id": "login-submit"}, None),
    ]


def explore_plan(story_id: str):
    plans = {
        "STORY-101": [
            ("Trying a wrong password three times through the API (AC3).", "http",
             {"method": "POST", "path": "/api/auth/login", "json": {"username": "amira", "password": "guess-1"}}, None),
            (None, "http", {"method": "POST", "path": "/api/auth/login", "json": {"username": "amira", "password": "guess-2"}}, None),
            (None, "http", {"method": "POST", "path": "/api/auth/login", "json": {"username": "amira", "password": "guess-3"}}, None),
            *_sign_in_steps(thought="Now the correct password on the web: after 3 failures the account must be locked."),
            ("Reading the screen to see where I landed.", "browser_read", {},
             lambda out, ctx: ("Account not locked after 3 failed sign-ins: the 4th attempt with the right password "
                               "signs in", "AC3", "high", f"3 × POST /api/auth/login (wrong) then web sign-in → {out['url']}")
             if "/dashboard" in out.get("url", "") else None),
        ],
        "STORY-102": [
            *_sign_in_steps(),
            ("Reading the accounts page: the total must equal the sum of the account cards (AC3).", "browser_read", {},
             lambda out, ctx: (lambda total, cards: (
                 f"Total balance shows {_el(out, 'total-balance')} but the accounts add up to EGP {cards:,.2f}",
                 "AC3", "high", f"Accounts page: cards {cards:,.2f} vs total {total:,.2f}")
                 if total is not None and abs(total - cards) > 0.001 else None)(
                 _money(_el(out, "total-balance")),
                 sum(_money(e["text"]) or 0 for e in out.get("elements", []) if e["id"].startswith("account-balance-")))),
        ],
        "STORY-103": [
            *_sign_in_steps(),
            ("Moving EGP 100.00 from current to savings on the transfer screen (AC1).", "browser_open", {"path": "/transfer"}, None),
            (None, "browser_select", {"test_id": "transfer-to", "value": "acc:SAV-1002"}, None),
            (None, "browser_fill", {"test_id": "transfer-amount-input", "text": "100.00"}, None),
            (None, "browser_click", {"test_id": "transfer-submit"},
             lambda out, ctx: None if _el(out, "transfer-success") else
             ("Own transfer did not confirm", "AC1", "high", out.get("text", "")[:200])),
            ("Trying to overdraw through the API, which must be refused (AC2).", "http",
             {"method": "POST", "path": "/api/auth/login", "json": {"username": "amira", "password": "Nile@2026"}},
             lambda out, ctx: _store_token(out, ctx)),
            (None, "http", lambda ctx: {"method": "POST", "path": "/api/transfers", "headers": _auth(ctx),
                                        "json": {"from_account": "CUR-1001", "to_account": "SAV-1002", "amount": 999999}},
             lambda out, ctx: None if out.get("status") == 409 else
             ("Overdraw accepted", "AC2", "critical", json.dumps(out)[:200])),
        ],
        "STORY-104": [
            ("Signing in through the API to probe the daily limit quickly.", "http",
             {"method": "POST", "path": "/api/auth/login", "json": {"username": "amira", "password": "Nile@2026"}},
             lambda out, ctx: _store_token(out, ctx)),
            ("Sending EGP 30,000 to Omar: within the EGP 50,000 daily limit.", "http",
             lambda ctx: {"method": "POST", "path": "/api/transfers", "headers": _auth(ctx),
                          "json": {"from_account": "SAV-1002", "beneficiary_id": 1, "amount": 30000}}, None),
            ("Sending another EGP 30,000 the same day: the running total would be 60,000 (AC2).", "http",
             lambda ctx: {"method": "POST", "path": "/api/transfers", "headers": _auth(ctx),
                          "json": {"from_account": "SAV-1002", "beneficiary_id": 1, "amount": 30000}},
             lambda out, ctx: ("Daily beneficiary limit not enforced across transfers: EGP 60,000 sent in one day",
                               "AC2", "critical", f"2nd POST /api/transfers 30,000 → {out.get('status')} "
                               f"{json.dumps(out.get('response') or out.get('body'))[:160]}")
             if out.get("status") == 201 else None),
            *_sign_in_steps(thought="Checking what the customer sees on the accounts page afterwards."),
            (None, "browser_read", {}, None),
        ],
        "STORY-105": [
            *_sign_in_steps(),
            ("Adding a beneficiary with an IBAN that is far too short, and HTML in the nickname (AC2, AC4).",
             "browser_open", {"path": "/beneficiaries"}, None),
            (None, "browser_fill", {"test_id": "beneficiary-nickname-input", "text": "<b>Laila</b>"}, None),
            (None, "browser_fill", {"test_id": "beneficiary-iban-input", "text": "EG123"}, None),
            (None, "browser_click", {"test_id": "beneficiary-submit"},
             lambda out, ctx: ("Invalid IBAN 'EG123' accepted (must be EG + 27 digits)", "AC2", "medium",
                               f"Beneficiaries screen: {_el(out, 'beneficiary-success')}")
             if _el(out, "beneficiary-success") else None),
            ("Looking at how the nickname is displayed in the list.", "browser_read", {},
             lambda out, ctx: (lambda html: ("Nickname HTML is rendered as markup (stored XSS risk)", "AC4", "critical",
                                             f"Typed '<b>Laila</b>', the list cell contains HTML: {html}")
                               if "<b>" in (html or "") else None)(
                 next((e["html"] for e in reversed(out.get("elements", [])) if e["id"] == "beneficiary-nickname"), ""))),
        ],
        "STORY-106": [
            ("Signing in through the API to page through the history.", "http",
             {"method": "POST", "path": "/api/auth/login", "json": {"username": "amira", "password": "Nile@2026"}},
             lambda out, ctx: _store_token(out, ctx)),
            ("Reading page 1 of the current account.", "http",
             lambda ctx: {"method": "GET", "path": "/api/accounts/CUR-1001/transactions?page=1", "headers": _auth(ctx)},
             lambda out, ctx: ctx.update(p1=[t["id"] for t in out["body"]["items"]]) or None),
            ("Reading page 2: no transaction may appear on both pages (AC2).", "http",
             lambda ctx: {"method": "GET", "path": "/api/accounts/CUR-1001/transactions?page=2", "headers": _auth(ctx)},
             lambda out, ctx: (lambda dup: (f"Transaction #{dup[0]} appears on page 1 and page 2", "AC2", "medium",
                                            f"page 1 ids {ctx['p1']}, page 2 ids {[t['id'] for t in out['body']['items']]}")
                               if dup else None)(
                 sorted(set(ctx["p1"]) & {t["id"] for t in out["body"]["items"]}))),
            *_sign_in_steps(thought="Checking the history screen as the customer sees it."),
            (None, "browser_open", {"path": "/history?account=CUR-1001&p=2"}, None),
        ],
        "STORY-107": [
            ("Signing in through the API.", "http",
             {"method": "POST", "path": "/api/auth/login", "json": {"username": "amira", "password": "Nile@2026"}},
             lambda out, ctx: _store_token(out, ctx)),
            ("Signing out with the same token.", "http",
             lambda ctx: {"method": "POST", "path": "/api/auth/logout", "headers": _auth(ctx)}, None),
            ("Reusing the token after sign-out: it must be rejected (AC3).", "http",
             lambda ctx: {"method": "GET", "path": "/api/accounts", "headers": _auth(ctx)},
             lambda out, ctx: ("Session token still works after sign-out", "AC3", "critical",
                               f"GET /api/accounts with the signed-out token → {out.get('status')}")
             if out.get("status") == 200 else None),
            *_sign_in_steps(thought="On the web: signing in, then signing out."),
            (None, "browser_click", {"test_id": "logout-link"}, None),
            ("Opening the accounts page after signing out.", "browser_open", {"path": "/dashboard"},
             lambda out, ctx: None if "/login" in out.get("url", "") else
             ("Accounts page reachable after sign-out", "AC2", "critical", out.get("url", ""))),
        ],
    }
    return plans.get(story_id, [])
