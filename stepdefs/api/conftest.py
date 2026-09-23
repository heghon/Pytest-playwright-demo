import json
import os
import pytest
from pytest_bdd import then, parsers
from api.base_api_client import BaseApiClient
from api.dummyjson.auth_api_client import AuthApiClient
from api.dummyjson.products_api_client import ProductsApiClient
from api.schema_validation import assert_matches_schema, load_schema
from stepdefs.conftest import report_note

# Public demo API, and public demo credentials published in its own docs. They
# live in .env like every other setting so pointing the suite at something else
# needs no code change, but they carry defaults so a fresh clone — and CI, whose
# DOTENV secret predates these tests — runs green without being configured first.
BASE_URL = os.getenv("DUMMYJSON_BASE_URL", "https://dummyjson.com")
USERNAME = os.getenv("DUMMYJSON_USERNAME", "emilys")
PASSWORD = os.getenv("DUMMYJSON_PASSWORD", "emilyspass")

# Generous enough that a slow public host is not mistaken for a broken one,
# short enough that a hung request fails the scenario instead of the job.
REQUEST_TIMEOUT_MS = 15_000


@pytest.fixture(autouse=True)
def _artifacts_dir():
    """
    Overrides the browser suite's fixture of the same name, deliberately.

    The version in stepdefs/conftest.py requests browser_name, which is what
    makes --browser work at all: pytest-playwright only parameterises a test
    across engines when it finds that fixture in the closure. An API test has
    no browser, so inheriting it would run every scenario once per engine for
    identical results, and label them with an engine that never started.

    Shadowing the name in a child conftest is pytest's own mechanism for "this
    subtree is different". There is nothing to record either: the artifacts it
    normally points at are screenshots, videos and traces, none of which exist
    without a page.
    """
    return None


"""
    A fresh APIRequestContext per scenario.

    It is Playwright's own HTTP client — the same driver as the browser tests,
    sharing their timeouts, but starting no browser.

    Function scope is not a detail. An APIRequestContext keeps a cookie jar,
    and /auth/login answers with accessToken and refreshToken cookies: share
    one context across the session and the scenario that checks the profile
    endpoint rejects an anonymous caller is quietly authenticated by the
    previous scenario's login, and gets a 200. A context is cheap precisely
    because no browser is involved, so there is nothing to save by reusing it
    and a false pass to be had by trying.
"""
@pytest.fixture
def api_request_context(playwright):
    context = playwright.request.new_context(
        base_url=BASE_URL,
        timeout=REQUEST_TIMEOUT_MS,
    )
    yield context
    context.dispose()


@pytest.fixture
def products_api(api_request_context):
    return ProductsApiClient(api_request_context)


@pytest.fixture
def auth_api(api_request_context):
    return AuthApiClient(api_request_context)


@pytest.fixture
def api_credentials():
    return {"username": USERNAME, "password": PASSWORD}


"""
    A scratchpad for the response under examination, passed from the step that
    sends a request to the steps that check it.

    target_fixture would not do here: a step can only inject a fixture under one
    fixed name, and a scenario that logs in and then calls the endpoint the
    token unlocked has two responses in flight. One mutable holder keeps "the
    response" meaning the most recent one. A fixture rather than a module
    global, so pytest clears it between scenarios.
"""
@pytest.fixture
def api_call():
    return {}


@pytest.fixture
def api_tokens():
    """
    Whatever a scenario has logged in and earned. Separate from api_call
    because a token outlives the response it arrived in: the login response is
    replaced the moment the next request is sent, and the token still has to be
    there to authorise it.
    """
    return {}


# Keys whose values never belong in a report, wherever they turn up in a body.
# A report is a thing you publish to Pages and paste into a ticket; a working
# token in one is a working token in both.
SECRET_KEYS = {"accesstoken", "refreshtoken", "token", "password"}

# Long enough to recognise a payload, short enough that a step's notes stay a
# glance rather than a read. The full body is one click away in the trace.
PREVIEW_LIMIT = 170


def _redacted(value):
    if isinstance(value, dict):
        return {
            key: "***" if key.lower() in SECRET_KEYS else _redacted(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redacted(item) for item in value]
    return value


def _shortened(text: str) -> str:
    return text if len(text) <= PREVIEW_LIMIT else f"{text[:PREVIEW_LIMIT]}…"


def _preview(response) -> str:
    try:
        rendered = json.dumps(_redacted(response.json()), ensure_ascii=False)
    except ValueError:
        # Not JSON at all — which is itself the useful thing to see.
        return _shortened(response.text())
    return _shortened(rendered)


"""
    Stores the response, and leaves a trail of it in the report.

    An API scenario has nothing to look at: no screenshot, no video, and a row
    of green steps that could equally mean the right call was made or a
    completely different one. These two notes are the evidence — what went out,
    and what came back — written once here so every call reports itself the
    same way instead of each step inventing its own wording.
"""
def record(api_call, response, method, detail=None):
    api_call["response"] = response
    path = response.url.removeprefix(BASE_URL) or "/"
    context = f" ({detail})" if detail else ""
    report_note(f"{method} {path}{context} → {response.status} {response.status_text}")
    report_note(f"Body: {_preview(response)}")
    return response


def latest(api_call):
    if "response" not in api_call:
        raise AssertionError(
            "No API call has been made yet in this scenario — a When step has "
            "to send a request before a Then step can check the response."
        )
    return api_call["response"]


def body(api_call):
    return BaseApiClient.body_of(latest(api_call))


# ---------------------------------------------------------------------------
# Steps shared by every API feature. They sit in conftest.py because that is
# where pytest-bdd looks for step definitions that more than one feature needs;
# a step that belongs to a single feature stays in that feature's own module.
# ---------------------------------------------------------------------------


@then(parsers.parse("the response status should be {expected:d}"))
def check_status(api_call, expected):
    response = latest(api_call)
    if response.status == expected:
        return
    # An unexpected status explains itself in the body, so that goes into the
    # failure too — otherwise the report shows two numbers and no reason.
    raise AssertionError(
        f"Expected {expected} from {response.url}, got {response.status} "
        f"{response.status_text}.\nBody: {response.text()[:300]}"
    )


@then("the response should be JSON")
def check_json_content_type(api_call):
    response = latest(api_call)
    content_type = response.headers.get("content-type", "")
    assert "application/json" in content_type, (
        f"Expected a JSON content-type from {response.url}, got '{content_type}'."
    )


@then(parsers.parse('the response should match the "{schema}" schema'))
def check_schema(api_call, schema):
    assert_matches_schema(
        body(api_call), schema, f"response from {latest(api_call).url}"
    )
    # Names the contract that just held. "Matches the schema" on its own says
    # nothing about how much the schema actually demands — a green step against
    # an empty schema looks identical to this one.
    required = load_schema(schema).get("required", [])
    report_note(
        f"Matches api/schemas/{schema}.schema.json — "
        f"{len(required)} required fields: {', '.join(required)}"
    )


@then(parsers.parse('the error message should mention "{fragment}"'))
def check_error_message(api_call, fragment):
    message = body(api_call).get("message", "")
    assert fragment.lower() in message.lower(), (
        f"Expected the error to mention '{fragment}', got '{message}'."
    )
