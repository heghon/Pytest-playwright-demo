from playwright.sync_api import Page


class BasePage:
    """
    Every page object inherits from this class. It just stores a reference
    to the Playwright `page` so every subclass can use it via self.page.
    """

    def __init__(self, page: Page):
        self.page = page