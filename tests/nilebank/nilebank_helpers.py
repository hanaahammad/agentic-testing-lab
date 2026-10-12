"""Helpers shared by NileBank tests (importable from test modules: `from nilebank_helpers import ...`)."""
import os
import re

import requests

BASE_URL = (os.getenv("NILEBANK_URL") or os.getenv("BASE_URL") or "http://127.0.0.1:8001").rstrip("/")
HEADLESS = os.getenv("HEADED", "0") != "1"
TIMEOUT_MS = int(os.getenv("UI_TIMEOUT_MS", "5000"))


class Bank:
    """Thin HTTP client for the NileBank REST API."""

    def __init__(self, base_url: str):
        self.base = base_url
        self.s = requests.Session()
        self.token = None

    def _h(self):
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def get(self, path, **kw):
        return self.s.get(self.base + path, headers=self._h(), timeout=10, **kw)

    def post(self, path, json=None, **kw):
        return self.s.post(self.base + path, json=json, headers=self._h(), timeout=10, **kw)

    def login(self, username="amira", password="Nile@2026"):
        r = self.post("/api/auth/login", json={"username": username, "password": password})
        assert r.status_code == 200, f"setup failed: login {r.status_code} {r.text}"
        self.token = r.json()["token"]
        return self.token

    def balance(self, account_id):
        r = self.get("/api/accounts")
        assert r.status_code == 200, f"setup failed: {r.status_code} {r.text}"
        return next(a["balance"] for a in r.json() if a["id"] == account_id)


def money(text: str) -> float:
    """'EGP 1,234.50' -> 1234.5"""
    m = re.search(r"-?[\d,]+\.\d{2}", text or "")
    assert m, f"no money amount in {text!r}"
    return float(m.group(0).replace(",", ""))


def sign_in(page, username="amira", password="Nile@2026"):
    page.goto(BASE_URL + "/login")
    page.get_by_test_id("login-username").fill(username)
    page.get_by_test_id("login-password").fill(password)
    page.get_by_test_id("login-submit").click()
