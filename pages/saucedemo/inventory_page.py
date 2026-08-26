from playwright.sync_api import expect
from pages.base_page import BasePage


class InventoryPage(BasePage):
    def add_to_cart(self, item_test_id: str):
        self.wait_for_element(
            self.page.locator(".inventory_list"),
            error_message="Inventory list did not appear — login may have failed"
        )
        self.page.locator(f"[data-test='add-to-cart-{item_test_id}']").click()
        
    def expect_cart_count(self, count: int):
        expect(self.page.locator(".shopping_cart_badge")).to_have_text(str(count))

    def go_to_cart(self):
        self.page.locator(".shopping_cart_link").click()