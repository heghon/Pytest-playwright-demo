import base64
import pytest
from pytest_html import extras
from dotenv import load_dotenv

load_dotenv()

# Hook -> pytest's system for plugging into its own internal lifecycle
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    # let all the normal reporting logic run first, then let me get the result
    outcome = yield
    report = outcome.get_result()

    # Try to 
    if report.when == "call" and report.failed:
        # item is pytest's internal object representing the test that just ran
        # funcargs is a dictionary of every fixture value that test actually used, keyed by name
        # this line reliably grabs the live, still-open browser tab at the moment of failure, before pytest-playwright's own teardown closes it
        page = item.funcargs.get("page")
        if page is not None:
            try:
                # lines to take the screeshot, then change to the correct format when put into the report
                screenshot_bytes = page.screenshot()
                encoded = base64.b64encode(screenshot_bytes).decode("utf-8")
                report.extras = getattr(report, "extras", []) + [
                    extras.image(encoded, name="Screenshot on failure")
                ]
            except Exception:
                pass