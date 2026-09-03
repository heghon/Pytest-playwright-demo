import pytest
from pytest_bdd import scenarios, given, when, then, parsers
from pages.saucedemo.cart_page import CartPage
from pages.saucedemo.checkout_page import CheckoutPage

scenarios("automation/checkout.feature")


@given("I am logged in to SauceDemo", target_fixture="inventory_page")
def logged_in(logged_in_inventory_page):
    return logged_in_inventory_page


@when("I add the following items to the cart:")
def add_items(inventory_page, datatable):
    for row in datatable:
        inventory_page.add_to_cart(row[0].lower().replace(" ", "-"))


@then(parsers.parse("the cart badge should show {count:d}"))
def check_cart_badge(inventory_page, count):
    inventory_page.expect_cart_count(count)


@when("I go to the cart", target_fixture="cart_page")
def go_to_cart(inventory_page, page):
    inventory_page.go_to_cart()
    cart_page = CartPage(page)
    cart_page.expect_on_cart_page()
    return cart_page


@when("I proceed to checkout", target_fixture="checkout_page")
def proceed_to_checkout(cart_page, page):
    cart_page.checkout()
    return CheckoutPage(page)


@when("I fill in my checkout information:")
def fill_checkout_info(checkout_page, datatable):
    header, *rows = datatable
    row = rows[0]
    first_name = row[header.index("first_name")]
    last_name = row[header.index("last_name")]
    zip_code = row[header.index("zip_code")]
    checkout_page.fill_info(first_name, last_name, zip_code)


@then("the overview should list:")
def check_overview_items(checkout_page, datatable):
    expected_names = [row[0] for row in datatable]
    checkout_page.expect_items_in_overview(expected_names)


@then("I can finish my order and see the confirmation")
def finish_and_confirm(checkout_page):
    finish_order(checkout_page)
    check_confirmation(checkout_page)

@when("I finish my order")
def finish_order(checkout_page):
    checkout_page.finish()


@then("I should see my order confirmation")
def check_confirmation(checkout_page):
    checkout_page.expect_order_complete()