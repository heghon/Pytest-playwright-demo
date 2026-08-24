import os
from dotenv import load_dotenv
from playwright.sync_api import Page, expect

load_dotenv()  # reads .env and loads its values into the environment

USERNAME = os.getenv("SAUCEDEMO_USERNAME")
PASSWORD = os.getenv("SAUCEDEMO_PASSWORD")

def test_login_add_to_cart_and_checkout(page: Page):
    # 1. Go to the login page
    page.goto("https://www.saucedemo.com/")

    # 2. Fill in the login form using SauceDemo's published test credentials
    page.get_by_placeholder("Username").fill(USERNAME)
    page.get_by_placeholder("Password").fill(PASSWORD)
    page.get_by_role("button", name="Login").click()

    # 3. Confirm login succeeded by checking we're on the inventory page
    expect(page).to_have_url("https://www.saucedemo.com/inventory.html")

    # 4. Add a specific product to the cart, identified by its data-test id
    page.locator("[data-test='add-to-cart-sauce-labs-backpack']").click()

    # 5. Assert the cart icon badge shows "1" item
    cart_badge = page.locator(".shopping_cart_badge")
    expect(cart_badge).to_have_text("1")

    # 6. Go to the cart
    page.locator(".shopping_cart_link").click()
    expect(page).to_have_url("https://www.saucedemo.com/cart.html")

    # 7. Proceed to checkout
    page.get_by_role("button", name="Checkout").click()

    # 8. Fill in the checkout info form
    page.get_by_placeholder("First Name").fill("Ada")
    page.get_by_placeholder("Last Name").fill("Lovelace")
    page.get_by_placeholder("Zip/Postal Code").fill("75000")
    page.get_by_role("button", name="Continue").click()

    # 9. Confirm we reached the checkout overview page with our item listed
    expect(page.locator(".inventory_item_name")).to_have_text("Sauce Labs Backpack")

    # 10. Finish the order
    page.get_by_role("button", name="Finish").click()

    # 11. Assert the final confirmation message appears
    expect(page.get_by_text("Thank you for your order!")).to_be_visible()