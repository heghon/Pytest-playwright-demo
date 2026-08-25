from playwright.sync_api import expect
from pages.base_page import BasePage


class CheckoutPage(BasePage):
    def fill_info(self, first_name: str, last_name: str, zip_code: str):
        self.page.get_by_placeholder("First Name").fill(first_name)
        self.page.get_by_placeholder("Last Name").fill(last_name)
        self.page.get_by_placeholder("Zip/Postal Code").fill(zip_code)
        self.page.get_by_role("button", name="Continue").click()

    def expect_item_in_overview(self, name: str):
        expect(self.page.locator(".inventory_item_name")).to_have_text(name)

    def finish(self):
        self.page.get_by_role("button", name="Finish").click()

    def expect_order_complete(self):
        expect(self.page.get_by_text("Thank you for your order!")).to_be_visible()