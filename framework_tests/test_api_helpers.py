"""
The pieces the API scenarios are built on: schema validation, the JSON body
reader, and the redacted previews that end up in the report.
"""

import json
from types import SimpleNamespace

import pytest

from api.base_api_client import BaseApiClient
from api.schema_validation import assert_matches_schema, load_schema
from stepdefs.api.conftest import PREVIEW_LIMIT, _preview, _redacted, _shortened, latest


def _response(payload=None, text="", content_type="application/json"):
    """A stand-in for Playwright's APIResponse, with only what the helpers read."""

    def read_json():
        if payload is None:
            raise ValueError("not JSON")
        return payload

    return SimpleNamespace(
        url="https://api.test/thing",
        json=read_json,
        text=lambda: text,
        headers={"content-type": content_type},
    )


# --- schemas -----------------------------------------------------------------


def _product():
    """A product that satisfies every requirement of the product schema."""
    return {
        "id": 1,
        "title": "Lamp",
        "category": "home",
        "price": 9.99,
        "rating": 4.5,
        "stock": 3,
        "tags": ["light"],
        "dimensions": {"width": 1, "height": 2, "depth": 3},
        "thumbnail": "https://img.test/lamp.png",
    }


def test_schema_load():
    """A schema is read from api/schemas/ by its name."""
    assert "price" in load_schema("product")["required"]


def test_schema_unknown():
    """An unknown schema name lists the schemas that do exist."""
    with pytest.raises(AssertionError) as error:
        load_schema("prodcut")
    message = str(error.value)
    assert "There is no 'prodcut' schema" in message
    assert "Available: error, product, product_page, user." in message


def test_schema_valid():
    """A payload matching its schema passes silently."""
    assert_matches_schema(_product(), "product")


def test_schema_all_errors():
    """Every violation is reported in one go, each with its JSON path."""
    product = _product()
    product["price"] = -1
    product["dimensions"]["width"] = "wide"

    with pytest.raises(AssertionError) as error:
        assert_matches_schema(product, "product", "product 1")

    message = str(error.value)
    assert "The product 1 does not match the 'product' schema (2 problems)" in message
    assert "$.dimensions.width:" in message
    assert "$.price:" in message


def test_schema_one_error():
    """A single violation reads "1 problem", in the singular."""
    with pytest.raises(AssertionError, match=r"\(1 problem\)"):
        assert_matches_schema({}, "error")


# --- reading a body ----------------------------------------------------------


def test_body_json():
    """A JSON body comes back as Python."""
    assert BaseApiClient.body_of(_response({"id": 1})) == {"id": 1}


def test_body_not_json():
    """A body that isn't JSON fails with the URL, content-type and what came back."""
    response = _response(text="<html>Bad gateway</html>", content_type="text/html")

    with pytest.raises(AssertionError) as error:
        BaseApiClient.body_of(response)

    message = str(error.value)
    assert "Expected JSON from https://api.test/thing, got text/html" in message
    assert "<html>Bad gateway</html>" in message
    # Replaces the decode error rather than chaining onto it.
    assert error.value.__suppress_context__


def test_latest_none():
    """Checking a response before any request explains the step order."""
    with pytest.raises(AssertionError, match="No API call has been made yet"):
        latest({})


def test_latest():
    """The latest response is the one last recorded."""
    response = _response({})
    assert latest({"response": response}) is response


# --- what the report shows ---------------------------------------------------


def test_redacted():
    """Secrets are masked at any depth, in dicts and lists, whatever their case."""
    body = {
        "accessToken": "a",
        "user": {"Password": "p", "name": "Emily"},
        "sessions": [{"refreshToken": "r", "id": 1}],
    }
    assert _redacted(body) == {
        "accessToken": "***",
        "user": {"Password": "***", "name": "Emily"},
        "sessions": [{"refreshToken": "***", "id": 1}],
    }


def test_preview_short():
    """A preview up to the limit is left whole."""
    text = "x" * PREVIEW_LIMIT
    assert _shortened(text) == text


def test_preview_long():
    """A preview over the limit is cut, and ends with an ellipsis to say so."""
    assert _shortened("x" * (PREVIEW_LIMIT + 1)) == "x" * PREVIEW_LIMIT + "…"


def test_preview_json():
    """A JSON body is previewed with its secrets masked."""
    preview = _preview(_response({"token": "secret", "id": 1}))
    assert json.loads(preview) == {"token": "***", "id": 1}


def test_preview_text():
    """A body that isn't JSON is previewed as its raw text."""
    assert _preview(_response(text="plain words")) == "plain words"
