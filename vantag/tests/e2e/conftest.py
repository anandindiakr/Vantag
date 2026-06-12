"""Shared Playwright fixtures for Vantag E2E tests."""
import pytest
from playwright.sync_api import Playwright, Browser, BrowserContext, Page

BASE_URL = "http://localhost:3000"


@pytest.fixture(scope="session")
def browser_type_launch_args():
    return {"headless": True, "args": ["--no-sandbox", "--disable-setuid-sandbox"]}


@pytest.fixture(scope="session")
def browser(playwright: Playwright, browser_type_launch_args):
    b = playwright.chromium.launch(**browser_type_launch_args)
    yield b
    b.close()


@pytest.fixture
def context(browser: Browser):
    ctx = browser.new_context(base_url=BASE_URL, ignore_https_errors=True)
    yield ctx
    ctx.close()


@pytest.fixture
def page(context: BrowserContext) -> Page:
    p = context.new_page()
    p.set_default_timeout(20_000)
    yield p
    p.close()
