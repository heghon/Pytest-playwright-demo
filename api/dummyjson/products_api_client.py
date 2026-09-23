from playwright.sync_api import APIResponse
from api.base_api_client import BaseApiClient


class ProductsApiClient(BaseApiClient):
    """
    The product catalog endpoints.

    Every method hands back the raw APIResponse rather than a parsed body: a
    scenario about a 404 needs the status code, and unpacking the body here
    would throw it away before the test ever saw it.
    """

    def get_product(self, product_id) -> APIResponse:
        return self.request.get(f"/products/{product_id}")

    def list_products(self, limit: int = 10, skip: int = 0) -> APIResponse:
        return self.request.get("/products", params={"limit": limit, "skip": skip})

    def search_products(self, term: str) -> APIResponse:
        return self.request.get("/products/search", params={"q": term})
