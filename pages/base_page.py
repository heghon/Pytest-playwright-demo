from playwright.sync_api import Page, Locator, TimeoutError as PlaywrightTimeoutError


class BasePage:
    """
    Every page object inherits from this class. It just stores a reference
    to the Playwright `page` so every subclass can use it via self.page.
    """

    def __init__(self, page: Page):
        self.page = page

    """
    Waits for a locator to become visible within `timeout` milliseconds.
    Raises a clear, custom error instead of Playwright's default timeout
    error, which can be harder to read at a glance.
    """
    def wait_for_element(self, locator: Locator, timeout: int = 5, error_message: str = None) -> Locator:
        try:
            locator.wait_for(state="visible", timeout=timeout*1000)
            return locator
        except PlaywrightTimeoutError:
            message = error_message or f"Element not visible after {timeout}s with locator: {locator}"
            raise AssertionError(message)

    """
    Fills a field and verifies the value actually 'stuck', else retrying a
    few times — guards against a stray dropped keystroke or the
    field not being fully ready yet.
    """
    def safe_fill(self, locator: Locator, text: str, retries: int = 3):
        actual_value = None
        for attempt in range(1, retries + 1):
            locator.fill(text)
            actual_value = locator.input_value()
            if actual_value == text:
                return
        raise AssertionError(
            f"Failed to correctly fill field after {retries} attempts."
            f"Expected '{text}', got '{actual_value}'"
        )