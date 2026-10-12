"""Shared helpers for agent-generated tests (black-box: HTTP only)."""
import os

import pytest
import requests

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000").rstrip("/")


class Api:
    """Thin HTTP client around the application under test."""

    def __init__(self, base_url: str):
        self.base = base_url
        self.s = requests.Session()

    def get(self, path, **kw):
        return self.s.get(self.base + path, timeout=10, **kw)

    def post(self, path, json=None, **kw):
        return self.s.post(self.base + path, json=json, timeout=10, **kw)

    def create_account(self, owner="Test User", initial_deposit=0):
        r = self.post("/accounts", json={"owner": owner, "initial_deposit": initial_deposit})
        assert r.status_code == 201, f"setup failed: {r.status_code} {r.text}"
        return r.json()

    def balance(self, account_id):
        r = self.get(f"/accounts/{account_id}")
        assert r.status_code == 200, f"setup failed: {r.status_code} {r.text}"
        return r.json()["balance"]


@pytest.fixture
def api():
    """A client on a freshly reset application."""
    client = Api(BASE_URL)
    client.post("/reset")
    return client
