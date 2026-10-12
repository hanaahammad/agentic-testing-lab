"""Shared helpers for agent-generated NileBank tests. Black box: HTTP API and the browser only.

Fixtures
  bank           API client on freshly reset demo data (not signed in)
  amira          API client already signed in as amira / Nile@2026
  page           a fresh Playwright browser page (headless Chromium)
  signed_in      a Playwright page already signed in as amira, on the accounts page
UI helpers (import them: from nilebank_helpers import sign_in, money)
  sign_in(page, username, password)   fills the sign-in form and submits it
  money(text) -> float                "EGP 1,234.50" -> 1234.5
"""
import pytest
import requests

from nilebank_helpers import BASE_URL, HEADLESS, TIMEOUT_MS, Bank, launch_browser, sign_in  # noqa: F401


@pytest.fixture(autouse=True)
def _fresh_data():
    """Every test starts from the same seeded data."""
    requests.post(BASE_URL + "/api/test/reset", timeout=10)


@pytest.fixture
def bank():
    return Bank(BASE_URL)


@pytest.fixture
def amira(bank):
    bank.login("amira", "Nile@2026")
    return bank


@pytest.fixture(scope="session")
def _browser():
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    browser = launch_browser(pw, headless=HEADLESS)
    yield browser
    browser.close()
    pw.stop()


@pytest.fixture
def page(_browser):
    ctx = _browser.new_context(viewport={"width": 1280, "height": 800}, base_url=BASE_URL)
    p = ctx.new_page()
    p.set_default_timeout(TIMEOUT_MS)
    yield p
    ctx.close()


@pytest.fixture
def signed_in(page):
    sign_in(page)
    page.wait_for_url("**/dashboard")
    return page
