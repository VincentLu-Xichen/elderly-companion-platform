from __future__ import annotations

import os
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright


BASE_URL = os.getenv("COURSE_SMOKE_BASE_URL", "http://127.0.0.1:8765")
INVITE_CODE = os.getenv("COURSE_SMOKE_INVITE", "course-smoke-invite")
SCREENSHOT_DIR = Path(os.getenv("COURSE_SMOKE_SCREENSHOT_DIR", "test-results/cbt-course"))


def login(page: Page) -> None:
    page.goto(BASE_URL, wait_until="networkidle")
    page.locator("#invite-code").fill(INVITE_CODE)
    page.locator("#invite-form button").click()
    page.wait_for_url(f"{BASE_URL}/app")


def assert_no_horizontal_overflow(page: Page) -> None:
    overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
    assert not overflow, "page has horizontal overflow"


def capture_browser_errors(page: Page, errors: list[str]) -> None:
    page.on("pageerror", lambda error: errors.append(f"pageerror: {error}"))
    page.on(
        "console",
        lambda message: errors.append(f"console: {message.text}")
        if message.type == "error"
        else None,
    )


def main() -> None:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)

        desktop = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = desktop.new_page()
        browser_errors: list[str] = []
        capture_browser_errors(page, browser_errors)
        login(page)
        page.locator("#consent-check").check()
        page.locator("#consent-button").click()
        page.wait_for_load_state("networkidle")
        page.locator("a.mode-card.cbt").click()
        page.wait_for_url(f"{BASE_URL}/cbt-course")
        expect(page.locator(".course-tile")).to_have_count(8)
        expect(page.locator("[data-start-lesson]")).to_have_count(1)
        expect(page.get_by_text("内容准备中")).to_have_count(7)
        assert_no_horizontal_overflow(page)
        page.screenshot(path=SCREENSHOT_DIR / "catalog-desktop.png", full_page=True)

        page.locator("[data-start-lesson='lesson-1']").click()
        page.wait_for_url(f"{BASE_URL}/cbt-course/conversations/**")
        page.wait_for_load_state("networkidle")
        expect(page.locator("#course-message-input")).to_be_visible()
        expect(page.locator("button")).to_have_count(1)
        expect(page.locator("input[type='radio'], input[type='range'], [role='option']")).to_have_count(0)
        expect(page.locator(".course-attachment img")).to_be_visible()
        self_pointer_events = page.locator(".course-attachment img").evaluate(
            "element => getComputedStyle(element).pointerEvents"
        )
        assert self_pointer_events == "none", "teaching image must not be interactive"
        assert_no_horizontal_overflow(page)
        page.screenshot(path=SCREENSHOT_DIR / "lesson-desktop.png", full_page=True, animations="disabled")

        page.locator("#course-message-input").fill("6")
        page.locator("#course-message-input").press("Enter")
        expect(page.locator(".course-message")).to_have_count(3)
        expect(page.locator("#course-phase")).to_have_text("我的案例")
        assert not browser_errors, browser_errors
        desktop.close()

        mobile = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=1)
        page = mobile.new_page()
        browser_errors = []
        capture_browser_errors(page, browser_errors)
        login(page)
        page.goto(f"{BASE_URL}/cbt-course", wait_until="networkidle")
        expect(page.locator(".course-tile")).to_have_count(8)
        assert_no_horizontal_overflow(page)
        page.screenshot(path=SCREENSHOT_DIR / "catalog-mobile.png", full_page=True)
        page.locator("[data-start-lesson='lesson-1']").click()
        page.wait_for_url(f"{BASE_URL}/cbt-course/conversations/**")
        page.wait_for_load_state("networkidle")
        expect(page.locator("button")).to_have_count(1)
        assert_no_horizontal_overflow(page)
        page.screenshot(path=SCREENSHOT_DIR / "lesson-mobile.png", animations="disabled")
        assert not browser_errors, browser_errors
        mobile.close()
        browser.close()

    print(f"Playwright course smoke passed; screenshots: {SCREENSHOT_DIR.resolve()}")


if __name__ == "__main__":
    main()
