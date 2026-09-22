from playwright.sync_api import expect
from pages.base_page import BasePage


class LoginPage(BasePage):
    URL = "https://www.saucedemo.com/"

    def goto(self):
        self.page.goto(self.URL)

    def login(self, username: str, password: str):
        self.safe_fill(self.page.get_by_placeholder("Username"), username)
        self.safe_fill(self.page.get_by_placeholder("Password"), password)
        self.wait_for_element(self.page.get_by_role("button", name="Login")).click()

    def expect_login_success(self):
        expect(self.page).to_have_url("https://www.saucedemo.com/inventory.html")

    """
    Asserts a refused sign-in: the expected message is on screen *and* the
    browser is still on the login page. The URL half matters as much as the
    message — an error banner means nothing if the user got in anyway.
    """
    def expect_login_error(self, message: str):
        expect(self.page.locator('[data-test="error"]')).to_have_text(message)
        expect(self.page).to_have_url(self.URL)