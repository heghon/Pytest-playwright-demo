import pytest
import os
from dotenv import load_dotenv
from pages.saucedemo.login_page import LoginPage
from pages.saucedemo.inventory_page import InventoryPage
from pages.saucedemo.cart_page import CartPage
from pages.saucedemo.checkout_page import CheckoutPage

load_dotenv() # Load the .env values

USERNAME = os.getenv("SAUCEDEMO_USERNAME")
PASSWORD = os.getenv("SAUCEDEMO_PASSWORD")


@pytest.mark.automation
def test_login_add_to_cart_and_checkout(page, logged_in_inventory_page):

    inventory_page = logged_in_inventory_page
    inventory_page.add_to_cart("sauce-labs-backpack")
    inventory_page.expect_cart_count(1)
    inventory_page.go_to_cart()

    cart_page = CartPage(page)
    cart_page.expect_on_cart_page()
    cart_page.checkout()

    checkout_page = CheckoutPage(page)
    checkout_page.fill_info("Ada", "Lovelace", "75000")
    checkout_page.expect_item_in_overview("Sauce Labs Backpack")
    checkout_page.finish()
    checkout_page.expect_order_complete()