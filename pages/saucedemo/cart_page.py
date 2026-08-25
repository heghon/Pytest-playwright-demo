from playwright.sync_api import expect
from pages.base_page import BasePage


class CartPage(BasePage):
    URL = "https://www.saucedemo.com/cart.html"

    def expect_on_cart_page(self):
        expect(self.page).to_have_url(self.URL)

    def checkout(self):
        self.page.get_by_role("button", name="Checkout").click()