import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from pytest_bdd import scenarios, given, when, then, parsers
from stepdefs.api.conftest import REQUEST_TIMEOUT_MS, body, record

scenarios("api/smoke.feature")


# Every field the product schema requires, so a stub product only has to name
# what the scenario is about and still passes schema validation like a real one.
PRODUCT_DEFAULTS = {
    "category": "smoke",
    "rating": 5,
    "stock": 1,
    "tags": ["smoke"],
    "dimensions": {"width": 1, "height": 1, "depth": 1},
    "thumbnail": "https://example.invalid/smoke.png",
}


@pytest.fixture
def stub_server():
    """
    A local HTTP server answering GET /products/<id> the way dummyjson does:
    the product as JSON, or a 404 whose message names the id.

    Started on a free port on 127.0.0.1 and stopped after the scenario, so the
    smoke check needs no network and no secrets. Which products it serves is
    up to the scenario: its catalog starts empty and a Given step fills it.
    """
    catalog = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            prefix = "/products/"
            product_id = self.path.removeprefix(prefix)
            if self.path.startswith(prefix) and product_id in catalog:
                self._answer(200, catalog[product_id])
            else:
                self._answer(404, {"message": f"Product with id '{product_id}' not found"})

        def _answer(self, status, payload):
            data = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format, *args):
            # Keeps the request log out of the captured output, and so out of
            # the report because the report_note from record() already says it all.
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    server.catalog = catalog
    server.url = f"http://127.0.0.1:{server.server_port}"
    yield server
    server.shutdown()
    server.server_close()


@pytest.fixture
def api_request_context(playwright, stub_server):
    """
    Overrides the context in stepdefs/api/conftest.py for this module only,
    pointing it at the stub instead of dummyjson. Everything built on it (the
    products_api client, record(), the shared Then steps) is the real thing.
    """
    context = playwright.request.new_context(
        base_url=stub_server.url,
        timeout=REQUEST_TIMEOUT_MS,
    )
    yield context
    context.dispose()


@given("the stub serves these products:", target_fixture="stub_products")
def stub_serves(stub_server, datatable):
    header, *rows = datatable
    for row in rows:
        fields = dict(zip(header, row))
        stub_server.catalog[fields["id"]] = {
            **PRODUCT_DEFAULTS,
            "id": int(fields["id"]),
            "title": fields["title"],
            "price": float(fields["price"]),
        }
    return stub_server.catalog


@when(parsers.parse('I request product "{product_id}" from the stub'))
def request_stub_product(products_api, api_call, product_id):
    record(api_call, products_api.get_product(product_id), "GET")


@then("the product should be the one the stub was given")
def check_stub_product(api_call, stub_products):
    product = body(api_call)
    expected = stub_products[str(product["id"])]
    assert product == expected, (
        f"The stub was given {expected}, the client read back {product}."
    )
