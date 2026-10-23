"""
The accessibility check's bookkeeping and report section, in
stepdefs/accessibility.py. Fed made-up axe-core responses on made-up URLs:
nothing here opens a browser.
"""

import pytest

from stepdefs import accessibility
from stepdefs.accessibility import (
    ELEMENTS_SHOWN,
    HTML_PREVIEW_CHARS,
    Results,
    _one_line,
    accessibility_note,
    section_html,
)

URL = "https://shop.test/"


def _violation(rule, impact, *targets):
    """One violation as axe-core reports it, found on these elements."""
    return {
        "id": rule,
        "impact": impact,
        "help": f"Help for {rule}",
        "helpUrl": f"https://rules.test/{rule}",
        "nodes": [{"target": [t], "html": f"<p id='{t}'>x</p>"} for t in targets],
    }


def _response(*violations):
    """A whole axe-core response, as axe-playwright-python returns it."""
    return {"testEngine": {"version": "9.9.9"}, "violations": list(violations)}


def _results(*responses, url=URL):
    """Results with these responses recorded against one page."""
    results = Results(enabled=True)
    for response in responses:
        results.record(url, "chromium", "A scenario", response)
    return results


# --- bookkeeping -------------------------------------------------------------


def test_merge_elements():
    """Two checks of one page list each element once, under one rule."""
    results = _results(
        _response(_violation("label", "critical", "#a", "#b")),
        _response(_violation("label", "critical", "#b", "#c")),
    )
    page = results.pages[(URL, "chromium")]
    assert page.checks == 2
    assert list(page.violations["label"].elements) == ["#a", "#b", "#c"]


def test_merge_scenarios():
    """A page checked by two scenarios names both, once each."""
    results = Results(enabled=True)
    for name in ("First", "Second", "First"):
        results.record(URL, "chromium", name, _response())
    assert results.pages[(URL, "chromium")].scenarios == ["First", "Second"]


def test_engines_apart():
    """The same page in two engines is two entries."""
    results = Results(enabled=True)
    results.record(URL, "chromium", "s", _response())
    results.record(URL, "firefox", "s", _response())
    assert set(results.pages) == {(URL, "chromium"), (URL, "firefox")}


def test_axe_version():
    """The axe-core version comes from the response itself."""
    assert _results(_response()).axe_version == "9.9.9"


# --- colours -----------------------------------------------------------------


@pytest.mark.parametrize(
    "impacts, colour",
    [
        (["critical"], "red"),
        (["serious", "minor"], "red"),
        (["moderate"], "orange"),
        (["minor"], "orange"),
        ([], "green"),
    ],
)
def test_colour(impacts, colour):
    """Red for critical or serious, orange for the rest, green for nothing."""
    found = [_violation(f"rule-{i}", impact, "#x") for i, impact in enumerate(impacts)]
    page = _results(_response(*found)).pages[(URL, "chromium")]
    assert page.colour() == colour


def test_colour_error():
    """A page the check could not run on is grey, and keeps the reason."""
    results = Results(enabled=True)
    results.record_error(URL, "chromium", "s", "Target page closed")
    page = results.pages[(URL, "chromium")]
    assert page.colour() == "grey"
    assert page.errors == ["Target page closed"]


# --- scenarios and accessibility_note ----------------------------------------


@pytest.fixture
def fresh(monkeypatch):
    """Empty, switched-on results, with no scenario running."""
    results = Results(enabled=True)
    monkeypatch.setattr(accessibility, "RESULTS", results)
    monkeypatch.setattr(accessibility, "_current", None)
    return results


def test_scenario_no_page(fresh):
    """A scenario that never opens a page leaves nothing in the results."""
    accessibility.start_scenario("An API scenario", "no browser")
    accessibility.end_scenario()
    assert fresh.pages == {}
    assert accessibility._current is None


def test_note_off(monkeypatch):
    """Without --accessibility, accessibility_note() does nothing at all."""
    monkeypatch.setattr(accessibility, "RESULTS", Results(enabled=False))
    accessibility_note(page=None)


def test_note_no_scenario(fresh):
    """accessibility_note() outside a scenario raises, like report_note."""
    with pytest.raises(RuntimeError, match="inside a scenario"):
        accessibility_note(page=None)


# --- the section -------------------------------------------------------------


def test_section_off():
    """With the check off, the report gets no section at all."""
    assert section_html(Results(enabled=False)) == ""


def test_section_order():
    """Pages are listed worst first: red, orange, green."""
    results = Results(enabled=True)
    results.record("https://c.test/", "chromium", "s", _response())
    results.record(
        "https://b.test/", "chromium", "s", _response(_violation("r", "minor", "#x"))
    )
    results.record(
        "https://a.test/", "chromium", "s", _response(_violation("r", "serious", "#x"))
    )
    html = section_html(results)
    assert html.index("a.test") < html.index("b.test") < html.index("c.test")


def test_section_escaped():
    """Markup from the checked page is shown as text, never run."""
    found = _violation("label", "critical", "#a")
    found["nodes"][0]["html"] = "<script>alert(1)</script>"
    html = section_html(_results(_response(found)))
    assert "<script>alert(1)" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_section_capped():
    """A rule on many elements lists the first few, then how many more."""
    targets = [f"#e{i}" for i in range(ELEMENTS_SHOWN + 4)]
    html = section_html(_results(_response(_violation("r", "minor", *targets))))
    assert html.count('class="a11y__target"') == ELEMENTS_SHOWN
    assert "…and 4 more" in html


def test_section_no_page():
    """A run where no scenario opened a page says so, with no entry at all."""
    html = section_html(Results(enabled=True))
    assert "No scenario in this run opened a page." in html
    assert "a11y__page" not in html


def test_one_line():
    """Element markup is put on one line and cut to the preview length."""
    assert _one_line("<div>\n   <p>hi</p>\n</div>") == "<div> <p>hi</p> </div>"
    long = "<p>" + "x" * HTML_PREVIEW_CHARS + "</p>"
    assert _one_line(long) == long[:HTML_PREVIEW_CHARS] + "…"
