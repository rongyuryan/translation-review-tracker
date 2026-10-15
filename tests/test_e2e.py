"""End-to-end browser tests with Playwright against a live local server."""

import pytest

playwright = pytest.importorskip("playwright.sync_api")

pytestmark = pytest.mark.e2e


@pytest.fixture
def page(live_server):
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(live_server)
        yield page
        browser.close()


def log_issue(page, line_ref, severity="medium", issue_type="tone"):
    page.fill("input[name=episode]", "EP01")
    page.fill("input[name=line_ref]", line_ref)
    page.fill("input[name=source_zh]", "你再说一遍试试？")
    page.fill("input[name=translation]", "You say it again and try?")
    page.fill("input[name=issue_type]", issue_type)
    page.select_option("select[name=severity]", severity)
    page.click("button[type=submit]")


def test_log_issue_appears_in_table(page):
    log_issue(page, "010", severity="high")
    row = page.locator("#issues tr").first
    row.wait_for()
    assert "EP01-010" in row.inner_text()
    assert "You say it again and try?" in row.inner_text()
    assert page.text_content("#stat-high") == "1"


def test_resolving_moves_issue_out_of_open_view(page):
    log_issue(page, "011")
    page.locator("#issues tr").first.wait_for()
    page.click("#issues button:has-text('Resolve')")
    page.wait_for_function("document.querySelector('#stat-resolved').textContent === '1'")
    assert page.locator("#issues tr").count() == 0

    page.select_option("#filter-status", "resolved")
    page.locator("#issues tr.resolved").first.wait_for()
    assert page.locator("#issues tr.resolved").count() == 1


def test_severity_filter(page):
    log_issue(page, "012", severity="low", issue_type="punctuation")
    page.wait_for_function("document.querySelectorAll('#issues tr').length === 1")
    log_issue(page, "013", severity="high", issue_type="number_mismatch")
    page.wait_for_function("document.querySelectorAll('#issues tr').length === 2")
    page.select_option("#filter-severity", "high")
    page.wait_for_function("document.querySelectorAll('#issues tr').length === 1")
    assert "number_mismatch" in page.locator("#issues tr").first.inner_text()


def test_validation_error_is_shown(page):
    page.evaluate("document.querySelector('#issue-form').noValidate = true")
    page.fill("input[name=episode]", "EP01")
    page.fill("input[name=line_ref]", "014")
    page.fill("input[name=source_zh]", "测试")
    page.click("button[type=submit]")
    page.wait_for_function("document.querySelector('#message').textContent.includes('issue_type')")
