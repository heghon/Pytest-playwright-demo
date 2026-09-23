from playwright.sync_api import APIRequestContext, APIResponse


class BaseApiClient:
    """
    Every API client inherits from this class, the way every page object
    inherits from BasePage. It holds the Playwright APIRequestContext — the
    same driver behind the browser tests, doing real HTTP with no browser
    started — so a client only has to describe its own endpoints.
    """

    def __init__(self, request_context: APIRequestContext):
        self.request = request_context

    """
    The response body as Python, with a readable failure when it isn't JSON.
    Playwright's own .json() raises a bare decode error that names neither the
    call that produced it nor what came back instead, which is a miserable
    thing to debug from a report.
    """
    @staticmethod
    def body_of(response: APIResponse) -> dict | list:
        try:
            return response.json()
        except ValueError:
            raise AssertionError(
                f"Expected JSON from {response.url}, got "
                f"{response.headers.get('content-type', 'no content-type')}:\n"
                f"{response.text()[:300]}"
            )
