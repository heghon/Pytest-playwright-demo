import os
from pytest_bdd import scenarios, given, when, then, parsers
from pages.saucedemo.login_page import LoginPage

scenarios("automation/login.feature")


"""
    The Examples table names each credential instead of spelling it out. The
    working password lives in .env like every other credential in this project,
    and the two broken ones only have to be wrong — what the row is testing is
    the point, not the exact string.
"""
USERNAMES = {
    "no username": "",
}

PASSWORDS = {
    "the valid password": os.getenv("SAUCEDEMO_PASSWORD", ""),
    "a wrong password": "definitely_not_the_password",
    "no password": "",
}


@given("I am on the SauceDemo login page", target_fixture="login_page")
def open_login_page(page):
    login_page = LoginPage(page)
    login_page.goto()
    return login_page


"""
    A username that isn't one of the names above is used as typed, so adding a
    row for another SauceDemo account needs nothing here. A password always is
    one of the names, so an unknown one is a typo in the feature file and says
    so, rather than failing later as a login that was never going to work.
"""
@when(parsers.parse("I log in as {username} with {password}"))
def attempt_login(login_page, username, password):
    if password not in PASSWORDS:
        raise ValueError(
            f"Unknown password in the Examples table: '{password}'. "
            f"Expected one of: {', '.join(PASSWORDS)}."
        )
    login_page.login(USERNAMES.get(username, username), PASSWORDS[password])


@then(parsers.parse('login should be refused with "{message}"'))
def check_login_refused(login_page, message):
    login_page.expect_login_error(message)
