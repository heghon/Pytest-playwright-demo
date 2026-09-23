from pytest_bdd import scenarios, when, then, parsers
from stepdefs.api.conftest import body, record
from stepdefs.conftest import report_note

scenarios("api/auth.feature")


@when("I log in to the API with valid credentials")
def login_with_valid_credentials(auth_api, api_call, api_credentials):
    # The username is worth seeing — it is configurable, so the report should
    # say which account a run actually used. Its password is not.
    record(
        api_call,
        auth_api.login(**api_credentials),
        "POST",
        f'as "{api_credentials["username"]}"',
    )


# Same convention as features/automation/login.feature: an Examples cell says
# "no username" rather than being left blank, because parse's {} placeholder
# compiles to .+? and will not match an empty string — a blank cell is reported
# as a missing step definition instead of as the validation check it is.
USERNAMES = {
    "no username": "",
}


@when(parsers.parse('I log in to the API as "{username}" with "{password}"'))
def login_as(auth_api, api_call, username, password):
    # These credentials are wrong on purpose and come from the Examples table,
    # so printing both is the point rather than a leak.
    record(
        api_call,
        auth_api.login(USERNAMES.get(username, username), password),
        "POST",
        f'as "{username}" with "{password}"',
    )


@then("the response should carry an access token")
def check_access_token(api_call, api_tokens):
    token = body(api_call).get("accessToken")
    assert token, "The login succeeded but returned no accessToken."
    api_tokens["access"] = token
    # Enough of it to recognise a JWT and to tell one run's token from
    # another's, and nowhere near enough of it to use.
    report_note(f"Access token received: {token[:18]}… ({len(token)} chars)")


@when("I request my own profile with that token")
def request_profile_with_token(auth_api, api_call, api_tokens):
    record(
        api_call,
        auth_api.get_current_user(api_tokens["access"]),
        "GET",
        "Authorization: Bearer <the token from the login above>",
    )


@when("I request my own profile with no token")
def request_profile_anonymously(auth_api, api_call):
    record(api_call, auth_api.get_current_user(), "GET", "no Authorization header")


"""
    Calls a protected endpoint with a token that is not one.

    The note is the point of this step. The API answers 500 where 401 belongs,
    so the scenario asserting 401 fails — and a red row with no explanation is
    indistinguishable from a broken test. The note says whose bug it is, right
    above the failure in the report, and it is conditional: fix the API and it
    stops being written at all.
"""
@when(parsers.parse('I request my own profile with the token "{token}"'))
def request_profile_with_bad_token(auth_api, api_call, token):
    response = record(
        api_call,
        auth_api.get_current_user(token),
        "GET",
        f'Authorization: Bearer {token}',
    )
    if response.status != 401:
        report_note(
            f"Heads up: the API answered {response.status}, not 401. A "
            "malformed token is a client error and belongs in a 401 — this is "
            "a defect in the API under test, not in the scenario."
        )
        report_note(
            "The assertion is deliberately written against the correct "
            "behaviour, so this scenario stays red until the API is fixed, and "
            "goes green by itself once it is."
        )


@then("the profile should belong to the account I logged in as")
def check_profile_identity(api_call, api_credentials):
    profile = body(api_call)
    username = profile.get("username")
    assert username == api_credentials["username"], (
        f"Logged in as '{api_credentials['username']}' but the profile "
        f"came back for '{username}'."
    )
    # Who the token actually turned out to belong to. The body preview above is
    # truncated well before the email, which is the field that identifies them.
    report_note(
        f"Token belongs to {username} — "
        f"{profile.get('firstName')} {profile.get('lastName')} "
        f"<{profile.get('email')}>"
    )
