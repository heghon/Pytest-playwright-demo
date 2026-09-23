from playwright.sync_api import APIResponse
from api.base_api_client import BaseApiClient


class AuthApiClient(BaseApiClient):
    """
    Logging in, and reaching an endpoint that insists on a token.

    A failed login is an ordinary outcome here rather than an error, so nothing
    in this class raises on a bad status — the scenario is what decides whether
    a 400 was the point or the problem.
    """

    def login(self, username: str, password: str) -> APIResponse:
        return self.request.post(
            "/auth/login", data={"username": username, "password": password}
        )

    """
    The profile of whoever the token belongs to. Called with no token at all to
    prove the endpoint is actually protected, so the header is only sent when
    there is one.
    """
    def get_current_user(self, token: str | None = None) -> APIResponse:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.request.get("/auth/me", headers=headers)
