"""MiniBank: the application under test.

A tiny core-banking REST API. It deliberately ships with seeded bugs so the QA
agent has something real to find. Set MINIBANK_FIXED=1 to run the "fixed"
build, which simulates a developer shipping the fixes.

Run it:  python -m uvicorn app_under_test.minibank:app --port 8000
Docs:    http://127.0.0.1:8000/docs  (the agent reads /openapi.json)
"""
import os
from decimal import Decimal, ROUND_HALF_UP
from threading import Lock

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

FIXED = os.getenv("MINIBANK_FIXED", "0") == "1"
BUILD = "fixed" if FIXED else "buggy"

app = FastAPI(
    title="MiniBank API",
    version="1.0.0",
    description="A tiny core-banking API used as the application under test.",
)

_lock = Lock()
_accounts: dict[str, dict] = {}
_transfers: list[dict] = []
_seq = {"acc": 0, "trf": 0}


class AccountIn(BaseModel):
    owner: str = Field(..., description="Account holder name")
    initial_deposit: float = Field(0.0, description="Opening balance")


class AmountIn(BaseModel):
    amount: float


class TransferIn(BaseModel):
    from_account: str
    to_account: str
    amount: float


def _money(x: float) -> float:
    """Round to 2 decimals, as a bank should."""
    if FIXED:
        return float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    return x  # seeded bug: no rounding, float artefacts leak into balances


def _get(account_id: str) -> dict:
    acc = _accounts.get(account_id)
    if acc is None:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")
    return acc


@app.get("/health", summary="Health check (also reports which build is running)")
def health():
    return {"status": "ok", "build": BUILD}


@app.post("/reset", summary="Test helper: wipe all accounts and transfers")
def reset():
    with _lock:
        _accounts.clear()
        _transfers.clear()
        _seq.update(acc=0, trf=0)
    return {"status": "reset"}


@app.post("/accounts", status_code=201, summary="Open an account")
def open_account(body: AccountIn):
    if not body.owner.strip():
        raise HTTPException(status_code=422, detail="owner must not be empty")
    if body.initial_deposit < 0:
        raise HTTPException(status_code=422, detail="initial_deposit must be >= 0")
    with _lock:
        _seq["acc"] += 1
        acc = {
            "id": f"ACC-{_seq['acc']:04d}",
            "owner": body.owner.strip(),
            "balance": _money(body.initial_deposit),
        }
        _accounts[acc["id"]] = acc
    return acc


@app.get("/accounts/{account_id}", summary="Get an account and its balance")
def get_account(account_id: str):
    return _get(account_id)


@app.post("/accounts/{account_id}/deposit", summary="Deposit money")
def deposit(account_id: str, body: AmountIn):
    acc = _get(account_id)
    if FIXED:
        if body.amount <= 0:
            raise HTTPException(status_code=422, detail="amount must be > 0")
    elif body.amount == 0:  # seeded bug: negative amounts slip through
        raise HTTPException(status_code=422, detail="amount must be > 0")
    with _lock:
        acc["balance"] = _money(acc["balance"] + body.amount)
    return acc


@app.post("/accounts/{account_id}/withdraw", summary="Withdraw money")
def withdraw(account_id: str, body: AmountIn):
    acc = _get(account_id)
    if body.amount <= 0:
        raise HTTPException(status_code=422, detail="amount must be > 0")
    if body.amount > acc["balance"]:
        raise HTTPException(status_code=409, detail="insufficient funds")
    with _lock:
        acc["balance"] = _money(acc["balance"] - body.amount)
    return acc


@app.post("/transfers", status_code=201, summary="Transfer money between accounts")
def transfer(body: TransferIn):
    if body.amount <= 0:
        raise HTTPException(status_code=422, detail="amount must be > 0")
    if body.from_account == body.to_account:
        raise HTTPException(status_code=422, detail="cannot transfer to the same account")
    src = _get(body.from_account)
    dst = _get(body.to_account)
    if FIXED and body.amount > src["balance"]:  # seeded bug: check missing in buggy build
        raise HTTPException(status_code=409, detail="insufficient funds")
    with _lock:
        src["balance"] = _money(src["balance"] - body.amount)
        dst["balance"] = _money(dst["balance"] + body.amount)
        _seq["trf"] += 1
        trf = {
            "id": f"TRF-{_seq['trf']:04d}",
            "from_account": src["id"],
            "to_account": dst["id"],
            "amount": _money(body.amount),
            "status": "completed",
        }
        _transfers.append(trf)
    return trf
