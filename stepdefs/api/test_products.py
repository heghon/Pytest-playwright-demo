from pytest_bdd import scenarios, when, then, parsers
from stepdefs.api.conftest import body, latest, record
from stepdefs.conftest import report_note
from api.schema_validation import assert_matches_schema

scenarios("api/products.feature")


@when(parsers.parse('I request product "{product_id}"'))
def request_product(products_api, api_call, product_id):
    record(api_call, products_api.get_product(product_id), "GET")


@when(parsers.parse("I request {limit:d} products starting from {skip:d}"))
def request_product_page(products_api, api_call, limit, skip):
    record(api_call, products_api.list_products(limit=limit, skip=skip), "GET")


@when(parsers.parse('I search the catalog for "{term}"'))
def search_catalog(products_api, api_call, term):
    record(api_call, products_api.search_products(term), "GET")


@then(parsers.parse("the page should hold exactly {count:d} products"))
def check_page_size(api_call, count):
    page = body(api_call)
    products = page["products"]
    assert len(products) == count, (
        f"Asked for {count} products, the page came back with {len(products)}."
    )
    # The size asked for is in the step; the size of the catalog behind it is
    # not, and it is what says whether this page is a slice or the whole thing.
    report_note(f"{len(products)} of {page['total']} products in the catalog")


@then(parsers.parse("the page should report a skip of {skip:d}"))
def check_page_skip(api_call, skip):
    reported = body(api_call)["skip"]
    assert reported == skip, f"Asked to skip {skip}, the page reports {reported}."


"""
    Validates each product in its own right rather than the array as a whole.

    A single schema over the list would name the failure "$.products[7].price",
    which means counting entries in a body of ten to find the culprit. Going one
    by one puts the product's own id and title in the message instead.
"""
@then(parsers.parse('every product on the page should match the "{schema}" schema'))
def check_every_product(api_call, schema):
    products = body(api_call)["products"]
    assert products, f"{latest(api_call).url} returned an empty page of products."
    for product in products:
        described = f"product {product.get('id', '?')} ({product.get('title', 'untitled')})"
        assert_matches_schema(product, schema, described)

    ids = [product.get("id") for product in products]
    counted = f"{len(products)} product{'' if len(products) == 1 else 's'}"
    span = f"id {ids[0]}" if len(ids) == 1 else f"ids {min(ids)}–{max(ids)}"
    report_note(f"{counted} validated against the '{schema}' schema — {span}")


@then(parsers.parse('every product on the page should mention "{term}"'))
def check_every_product_mentions(api_call, term):
    needle = term.lower()
    matched = []
    for product in body(api_call)["products"]:
        haystack = " ".join(
            str(product.get(field, ""))
            for field in ("title", "description", "category", "brand")
        ).lower()
        assert needle in haystack, (
            f"Product {product.get('id')} ({product.get('title')}) came back for "
            f"the search '{term}' but mentions it nowhere."
        )
        matched.append(product.get("title", "untitled"))

    # What the search actually returned, which is the one thing a green
    # "every product mentions it" step cannot tell you.
    report_note(f"Returned for '{term}': {', '.join(matched)}")
