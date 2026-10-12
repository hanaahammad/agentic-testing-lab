"""NileBank: a realistic online-banking web app used as the application under test.

It has a web UI (server-rendered pages with data-testid attributes for automation) AND a REST API,
a SQLite database, sign-in with sessions, and deliberately seeded bugs. Set NILEBANK_FIXED=1 to run
the "fixed" build, which simulates the developers shipping the fixes.

Run:   python -m uvicorn apps.nilebank.app:app --port 8001
Open:  http://127.0.0.1:8001          (sign in as amira / Nile@2026)
API:   http://127.0.0.1:8001/docs
"""
import datetime as dt
import os
import re
import secrets
import sqlite3
import tempfile
import threading
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

FIXED = os.getenv("NILEBANK_FIXED", "0") == "1"
BUILD = "fixed" if FIXED else "buggy"
HERE = Path(__file__).parent
DB_PATH = os.getenv("NILEBANK_DB") or str(Path(tempfile.gettempdir()) / f"nilebank_{os.getpid()}.db")

MAX_FAILED_LOGINS = 3
DAILY_BENEFICIARY_LIMIT = 50_000_00  # piasters (EGP 50,000.00)
PAGE_SIZE = 10
IBAN_RE = re.compile(r"^EG\d{27}$")

app = FastAPI(title="NileBank API", version="2.4.0",
              description="Online banking for NileBank customers: accounts, transfers, beneficiaries, history.")
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")

_lock = threading.RLock()


# ---------------------------------------------------------------- database
def db():
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


SCHEMA = """
DROP TABLE IF EXISTS users; DROP TABLE IF EXISTS accounts; DROP TABLE IF EXISTS sessions;
DROP TABLE IF EXISTS beneficiaries; DROP TABLE IF EXISTS transactions;
CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT, full_name TEXT,
                    failed_logins INTEGER DEFAULT 0, locked INTEGER DEFAULT 0);
CREATE TABLE accounts (id TEXT PRIMARY KEY, user_id INTEGER, kind TEXT, iban TEXT UNIQUE, balance INTEGER);
CREATE TABLE sessions (token TEXT PRIMARY KEY, user_id INTEGER, created TEXT);
CREATE TABLE beneficiaries (id INTEGER PRIMARY KEY, user_id INTEGER, nickname TEXT, iban TEXT);
CREATE TABLE transactions (id INTEGER PRIMARY KEY, account_id TEXT, ts TEXT, description TEXT,
                           amount INTEGER, kind TEXT);
"""

USERS = [  # username, password, full name
    ("amira", "Nile@2026", "Amira Hassan"),
    ("omar", "Pyramid#77", "Omar Farouk"),
]


def seed():
    with _lock:
        con = db()
        con.executescript(SCHEMA)
        for i, (u, p, n) in enumerate(USERS, 1):
            con.execute("INSERT INTO users (id, username, password, full_name) VALUES (?,?,?,?)", (i, u, p, n))
        con.executemany("INSERT INTO accounts VALUES (?,?,?,?,?)", [
            ("CUR-1001", 1, "Current account", "EG380019000500000000263180002", 25_000_00),
            ("SAV-1002", 1, "Savings account", "EG380019000500000000263180003", 100_000_00),
            ("CUR-2001", 2, "Current account", "EG380019000500000000263180101", 3_500_00),
        ])
        con.execute("INSERT INTO beneficiaries (user_id, nickname, iban) VALUES (1, 'Omar Farouk', "
                    "'EG380019000500000000263180101')")
        base = dt.datetime(2026, 9, 1, 9, 0)
        rows = []
        for n in range(25):  # 25 past transactions on Amira's current account, oldest first
            amt = (-1) ** n * (150_00 + n * 37_00)
            desc = ["Card payment · Carrefour Maadi", "Salary · WAVZ", "Card payment · Vodafone", "Transfer · Laila",
                    "ATM withdrawal · Zamalek"][n % 5]
            rows.append(("CUR-1001", (base + dt.timedelta(days=n)).isoformat(" ", "minutes"), f"{desc} #{n + 1:02d}",
                         amt, "card" if amt < 0 else "credit"))
        con.executemany("INSERT INTO transactions (account_id, ts, description, amount, kind) VALUES (?,?,?,?,?)", rows)
        con.commit()
        con.close()


seed()


def now():
    return dt.datetime.now().isoformat(" ", "seconds")


def egp(piasters: int) -> str:
    return f"EGP {piasters / 100:,.2f}"


def to_piasters(amount: float) -> int:
    return int(round(float(amount) * 100))


templates.env.filters["egp"] = egp


# ---------------------------------------------------------------- domain logic (shared by API and UI)
class BankError(Exception):
    def __init__(self, status: int, message: str):
        self.status, self.message = status, message


def authenticate(username: str, password: str) -> str:
    with _lock:
        con = db()
        u = con.execute("SELECT * FROM users WHERE username=?", (username.strip().lower(),)).fetchone()
        if u is None:
            raise BankError(401, "Invalid username or password.")
        if u["locked"]:
            raise BankError(423, "Your account is locked after too many failed sign-in attempts. Please call 19123.")
        if u["password"] != password:
            if FIXED:  # seeded bug: the buggy build never counts failed attempts, so it never locks
                failed = u["failed_logins"] + 1
                con.execute("UPDATE users SET failed_logins=?, locked=? WHERE id=?",
                            (failed, int(failed >= MAX_FAILED_LOGINS), u["id"]))
                con.commit()
                if failed >= MAX_FAILED_LOGINS:
                    raise BankError(423, "Your account is locked after too many failed sign-in attempts. "
                                         "Please call 19123.")
            raise BankError(401, "Invalid username or password.")
        con.execute("UPDATE users SET failed_logins=0 WHERE id=?", (u["id"],))
        token = secrets.token_urlsafe(24)
        con.execute("INSERT INTO sessions VALUES (?,?,?)", (token, u["id"], now()))
        con.commit()
        return token


def end_session(token: str):
    if not FIXED:  # seeded bug: buggy build forgets to revoke the session server-side
        return
    with _lock:
        con = db()
        con.execute("DELETE FROM sessions WHERE token=?", (token,))
        con.commit()


def user_for(token: str | None):
    if not token:
        return None
    con = db()
    return con.execute("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=?",
                       (token,)).fetchone()


def accounts_of(user_id: int):
    return [dict(r) for r in db().execute("SELECT * FROM accounts WHERE user_id=? ORDER BY id", (user_id,))]


def beneficiaries_of(user_id: int):
    return [dict(r) for r in db().execute("SELECT * FROM beneficiaries WHERE user_id=? ORDER BY id", (user_id,))]


def add_beneficiary(user_id: int, nickname: str, iban: str) -> dict:
    nickname, iban = nickname.strip(), iban.replace(" ", "").upper()
    if not nickname:
        raise BankError(422, "Please enter a nickname.")
    valid = IBAN_RE.match(iban) if FIXED else iban.startswith("EG")  # seeded bug: length never checked
    if not valid:
        raise BankError(422, "Please enter a valid Egyptian IBAN (EG followed by 27 digits).")
    with _lock:
        con = db()
        cur = con.execute("INSERT INTO beneficiaries (user_id, nickname, iban) VALUES (?,?,?)", (user_id, nickname, iban))
        con.commit()
        return {"id": cur.lastrowid, "nickname": nickname, "iban": iban}


def beneficiary_spent_today(con, user_id: int) -> int:
    today = dt.date.today().isoformat()
    row = con.execute("""SELECT COALESCE(SUM(-t.amount),0) FROM transactions t JOIN accounts a ON a.id=t.account_id
                         WHERE a.user_id=? AND t.kind='beneficiary' AND t.ts >= ?""", (user_id, today)).fetchone()
    return row[0]


def transfer(user_id: int, from_id: str, amount: float, to_account: str | None = None,
             beneficiary_id: int | None = None, note: str = "") -> dict:
    cents = to_piasters(amount)
    if cents <= 0:
        raise BankError(422, "The amount must be greater than zero.")
    if (to_account is None) == (beneficiary_id is None):
        raise BankError(422, "Choose either one of your accounts or a beneficiary as destination.")
    with _lock:
        con = db()
        src = con.execute("SELECT * FROM accounts WHERE id=? AND user_id=?", (from_id, user_id)).fetchone()
        if src is None:
            raise BankError(404, "Source account not found.")
        if to_account is not None:
            dst = con.execute("SELECT * FROM accounts WHERE id=? AND user_id=?", (to_account, user_id)).fetchone()
            if dst is None:
                raise BankError(404, "Destination account not found.")
            if dst["id"] == src["id"]:
                raise BankError(422, "Source and destination must be different accounts.")
            label, kind = f"Own transfer · {src['id']} → {dst['id']}", "own"
        else:
            ben = con.execute("SELECT * FROM beneficiaries WHERE id=? AND user_id=?", (beneficiary_id, user_id)).fetchone()
            if ben is None:
                raise BankError(404, "Beneficiary not found.")
            dst = con.execute("SELECT * FROM accounts WHERE iban=?", (ben["iban"],)).fetchone()  # internal or external
            label, kind = f"Transfer to {ben['nickname']}", "beneficiary"
            spent = beneficiary_spent_today(con, user_id)
            over = (spent + cents > DAILY_BENEFICIARY_LIMIT) if FIXED else (cents > DAILY_BENEFICIARY_LIMIT)
            if over:  # seeded bug: buggy build checks each transfer alone, not the running daily total
                left = max(0, DAILY_BENEFICIARY_LIMIT - spent)
                raise BankError(409, f"This transfer exceeds your daily limit of {egp(DAILY_BENEFICIARY_LIMIT)}. "
                                     f"You can still send {egp(left)} today.")
        if cents > src["balance"]:
            raise BankError(409, "Insufficient funds in the source account.")
        con.execute("UPDATE accounts SET balance=balance-? WHERE id=?", (cents, src["id"]))
        ts = now()
        con.execute("INSERT INTO transactions (account_id, ts, description, amount, kind) VALUES (?,?,?,?,?)",
                    (src["id"], ts, label + (f" · {note}" if note else ""), -cents, kind))
        if dst is not None:
            con.execute("UPDATE accounts SET balance=balance+? WHERE id=?", (cents, dst["id"]))
            con.execute("INSERT INTO transactions (account_id, ts, description, amount, kind) VALUES (?,?,?,?,?)",
                        (dst["id"], ts, f"Incoming · from {src['id']}", cents, "credit"))
        con.commit()
        ref = f"NB{secrets.randbelow(10**8):08d}"
        return {"reference": ref, "from_account": src["id"], "amount": cents / 100, "status": "completed",
                "new_balance": (src["balance"] - cents) / 100}


def history(user_id: int, account_id: str, page: int) -> dict:
    con = db()
    acc = con.execute("SELECT * FROM accounts WHERE id=? AND user_id=?", (account_id, user_id)).fetchone()
    if acc is None:
        raise BankError(404, "Account not found.")
    total = con.execute("SELECT COUNT(*) FROM transactions WHERE account_id=?", (account_id,)).fetchone()[0]
    pages = max(1, -(-total // PAGE_SIZE))
    page = min(max(1, page), pages)
    offset = (page - 1) * PAGE_SIZE
    if not FIXED and page > 1:
        offset -= 1  # seeded bug: off-by-one, each page repeats the last row of the previous page
    rows = con.execute("SELECT * FROM transactions WHERE account_id=? ORDER BY ts DESC, id DESC LIMIT ? OFFSET ?",
                       (account_id, PAGE_SIZE, offset)).fetchall()
    return {"account_id": account_id, "page": page, "pages": pages, "total": total,
            "items": [{"id": r["id"], "date": r["ts"], "description": r["description"],
                       "amount": r["amount"] / 100} for r in rows]}


def total_balance(accounts: list[dict]) -> int:
    if FIXED:
        return sum(a["balance"] for a in accounts)
    return accounts[0]["balance"] if accounts else 0  # seeded bug: "total" only counts the first account


# ---------------------------------------------------------------- REST API
class LoginIn(BaseModel):
    username: str
    password: str


class TransferIn(BaseModel):
    from_account: str
    amount: float
    to_account: str | None = None
    beneficiary_id: int | None = None
    note: str = ""


class BeneficiaryIn(BaseModel):
    nickname: str
    iban: str


def api_user(authorization: str | None = Header(None)):
    token = (authorization or "").removeprefix("Bearer ").strip()
    u = user_for(token)
    if u is None:
        raise HTTPException(401, "Not signed in or session expired.")
    return u, token


def run(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except BankError as e:
        raise HTTPException(e.status, e.message)


@app.get("/api/health", tags=["system"], summary="Health check (reports which build is running)")
def health():
    return {"status": "ok", "app": "nilebank", "build": BUILD}


@app.post("/api/test/reset", tags=["system"], summary="Test environments only: restore the seeded demo data")
def reset():
    seed()
    return {"status": "reset"}


@app.post("/api/auth/login", tags=["auth"], summary="Sign in and get a session token")
def api_login(body: LoginIn):
    return {"token": run(authenticate, body.username, body.password)}


@app.post("/api/auth/logout", tags=["auth"], summary="Sign out: the session token must stop working")
def api_logout(ctx=Depends(api_user)):
    end_session(ctx[1])
    return {"status": "signed out"}


@app.get("/api/me", tags=["auth"], summary="The signed-in customer")
def api_me(ctx=Depends(api_user)):
    u = ctx[0]
    return {"username": u["username"], "full_name": u["full_name"]}


@app.get("/api/accounts", tags=["accounts"], summary="List my accounts with balances")
def api_accounts(ctx=Depends(api_user)):
    accs = accounts_of(ctx[0]["id"])
    return [{"id": a["id"], "kind": a["kind"], "iban": a["iban"], "balance": a["balance"] / 100} for a in accs]


@app.get("/api/accounts/{account_id}/transactions", tags=["accounts"],
         summary="Transaction history, newest first, 10 per page")
def api_history(account_id: str, page: int = 1, ctx=Depends(api_user)):
    return run(history, ctx[0]["id"], account_id, page)


@app.get("/api/beneficiaries", tags=["beneficiaries"], summary="List my beneficiaries")
def api_beneficiaries(ctx=Depends(api_user)):
    return beneficiaries_of(ctx[0]["id"])


@app.post("/api/beneficiaries", tags=["beneficiaries"], status_code=201, summary="Add a beneficiary (valid IBAN)")
def api_add_beneficiary(body: BeneficiaryIn, ctx=Depends(api_user)):
    return run(add_beneficiary, ctx[0]["id"], body.nickname, body.iban)


@app.post("/api/transfers", tags=["transfers"], status_code=201,
          summary="Transfer to one of my accounts (to_account) or to a beneficiary (beneficiary_id)")
def api_transfer(body: TransferIn, ctx=Depends(api_user)):
    return run(transfer, ctx[0]["id"], body.from_account, body.amount, body.to_account, body.beneficiary_id, body.note)


# ---------------------------------------------------------------- web UI
COOKIE = "nb_session"


def page(request: Request, name: str, user=None, status: int = 200, **ctx):
    return templates.TemplateResponse(request, name, {"user": user, "build": BUILD, "fixed": FIXED, **ctx},
                                      status_code=status)


def web_user(request: Request):
    return user_for(request.cookies.get(COOKIE))


def to_login():
    return RedirectResponse("/login", status_code=303)


@app.get("/", include_in_schema=False)
def home(request: Request):
    return RedirectResponse("/dashboard" if web_user(request) else "/login", status_code=303)


@app.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login_page(request: Request):
    return page(request, "login.html")


@app.post("/login", include_in_schema=False)
def login_submit(request: Request, username: str = Form(""), password: str = Form("")):
    try:
        token = authenticate(username, password)
    except BankError as e:
        return page(request, "login.html", error=e.message, username=username, status=e.status)
    resp = RedirectResponse("/dashboard", status_code=303)
    resp.set_cookie(COOKIE, token, httponly=True, samesite="lax")
    return resp


@app.get("/logout", include_in_schema=False)
def logout(request: Request):
    token = request.cookies.get(COOKIE)
    if token:
        end_session(token)
    resp = RedirectResponse("/login?signed_out=1", status_code=303)
    resp.delete_cookie(COOKIE)
    return resp


@app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard(request: Request):
    u = web_user(request)
    if not u:
        return to_login()
    accs = accounts_of(u["id"])
    return page(request, "dashboard.html", u, accounts=accs, total=total_balance(accs), nav="dashboard")


@app.get("/transfer", response_class=HTMLResponse, include_in_schema=False)
def transfer_page(request: Request):
    u = web_user(request)
    if not u:
        return to_login()
    return page(request, "transfer.html", u, accounts=accounts_of(u["id"]), beneficiaries=beneficiaries_of(u["id"]),
                nav="transfer", limit=DAILY_BENEFICIARY_LIMIT)


@app.post("/transfer", response_class=HTMLResponse, include_in_schema=False)
def transfer_submit(request: Request, from_account: str = Form(...), destination: str = Form(...),
                    amount: str = Form(""), note: str = Form("")):
    u = web_user(request)
    if not u:
        return to_login()
    ctx = dict(accounts=accounts_of(u["id"]), beneficiaries=beneficiaries_of(u["id"]), nav="transfer",
               limit=DAILY_BENEFICIARY_LIMIT, form={"from_account": from_account, "destination": destination,
                                                    "amount": amount, "note": note})
    try:
        value = float(amount.replace(",", ""))
    except ValueError:
        return page(request, "transfer.html", u, error="Please enter a valid amount.", status=422, **ctx)
    kind, _, ref = destination.partition(":")
    try:
        res = transfer(u["id"], from_account, value, to_account=ref if kind == "acc" else None,
                       beneficiary_id=int(ref) if kind == "ben" else None, note=note)
    except BankError as e:
        return page(request, "transfer.html", u, error=e.message, status=e.status, **ctx)
    ctx["accounts"] = accounts_of(u["id"])
    ctx["form"] = {}
    return page(request, "transfer.html", u, result=res, **ctx)


@app.get("/beneficiaries", response_class=HTMLResponse, include_in_schema=False)
def beneficiaries_page(request: Request):
    u = web_user(request)
    if not u:
        return to_login()
    return page(request, "beneficiaries.html", u, beneficiaries=beneficiaries_of(u["id"]), nav="beneficiaries")


@app.post("/beneficiaries", response_class=HTMLResponse, include_in_schema=False)
def beneficiaries_submit(request: Request, nickname: str = Form(""), iban: str = Form("")):
    u = web_user(request)
    if not u:
        return to_login()
    try:
        b = add_beneficiary(u["id"], nickname, iban)
        msg, err, status = f"{b['nickname']} was added to your beneficiaries.", None, 201
    except BankError as e:
        msg, err, status = None, e.message, e.status
    return page(request, "beneficiaries.html", u, beneficiaries=beneficiaries_of(u["id"]), nav="beneficiaries",
                success=msg, error=err, form={"nickname": nickname, "iban": iban} if err else {}, status=status)


@app.get("/history", response_class=HTMLResponse, include_in_schema=False)
def history_page(request: Request, account: str = "", p: int = 1):
    u = web_user(request)
    if not u:
        return to_login()
    accs = accounts_of(u["id"])
    account = account or accs[0]["id"]
    try:
        h = history(u["id"], account, p)
    except BankError as e:
        return page(request, "history.html", u, accounts=accs, error=e.message, nav="history", status=e.status)
    return page(request, "history.html", u, accounts=accs, h=h, nav="history")
