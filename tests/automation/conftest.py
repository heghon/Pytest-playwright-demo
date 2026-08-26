import os
import pytest
from pages.saucedemo.login_page import LoginPage
from pages.saucedemo.inventory_page import InventoryPage

"""
    Logs in via SauceDemo and hands the test a ready-to-use InventoryPage,
    so individual tests don't repeat the login steps themselves.
"""
@pytest.fixture
def logged_in_inventory_page(page):
    login_page = LoginPage(page)
    login_page.goto()
    login_page.login(os.getenv("SAUCEDEMO_USERNAME"), os.getenv("SAUCEDEMO_PASSWORD"))
    login_page.expect_login_success()
    return InventoryPage(page)