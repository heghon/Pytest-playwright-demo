"""
The pass charts in stepdefs/charts.py: what each test counts as, and the donuts
drawn from the counts. Stand-ins for pytest's reports, no run needed.
"""

import re
from types import SimpleNamespace

from stepdefs.charts import Tally, donut, section_html


def _report(nodeid, outcome, folder="api", when="call", retry=""):
    """A stand-in for one phase's report, as the report hooks leave it."""
    return SimpleNamespace(
        nodeid=nodeid,
        when=when,
        outcome=outcome,
        failed=outcome == "failed",
        skipped=outcome == "skipped",
        group_folder=folder,
        retry=retry,
    )


def _tally(*reports):
    tally = Tally()
    for report in reports:
        tally.record(report)
    return tally


def test_segments():
    """Each test counts once, in the segment its final outcome puts it in."""
    tally = _tally(
        _report("a", "passed"),
        _report("b", "failed"),
        _report("c", "skipped"),
        _report("d", "passed", retry="passed"),
    )
    assert tally.counts() == {"passed": 1, "retried": 1, "failed": 1, "skipped": 1}


def test_rerun_ignored():
    """A failed attempt with a retry to come counts for nothing: the retry decides."""
    tally = _tally(_report("a", "rerun"), _report("a", "passed", retry="passed"))
    assert tally.counts()["retried"] == 1
    assert tally.counts()["failed"] == 0


def test_error_is_failed():
    """A teardown error counts as a failure."""
    tally = _tally(_report("a", "passed"), _report("a", "failed", when="teardown"))
    assert tally.counts()["failed"] == 1


def test_folders():
    """Folders come in the order their first test ran, each counted on its own."""
    tally = _tally(
        _report("a", "passed", folder="ui_testing"),
        _report("b", "failed", folder="api"),
        _report("c", "passed", folder="ui_testing"),
    )
    assert tally.folders() == ["ui_testing", "api"]
    assert tally.counts("ui_testing")["passed"] == 2


def _dashes(html):
    return [float(d) for d in re.findall(r'stroke-dasharray="([\d.]+) ', html)]


def test_donut_shares():
    """Segments split the ring by count, a gap apart, and only those present show."""
    html = donut({"passed": 3, "retried": 0, "failed": 1, "skipped": 0}, 120, 14, "x")
    assert "donut__seg--retried" not in html
    passed, failed = _dashes(html)
    assert round((passed + 2) / (failed + 2)) == 3


def test_donut_whole():
    """A single segment closes the ring, with no gap."""
    html = donut({"passed": 2, "retried": 0, "failed": 0, "skipped": 0}, 120, 14, "x")
    ring = float(re.search(r'stroke-dasharray="[\d.]+ ([\d.]+)"', html).group(1))
    assert _dashes(html) == [ring]


def test_donut_text():
    """The centre gives the passes, retries included, and each segment a tooltip."""
    html = donut({"passed": 3, "retried": 1, "failed": 1, "skipped": 0}, 84, 10, "api")
    assert ">4/5</span>" in html
    assert "<title>api · Failed: 1 of 5</title>" in html
    assert 'aria-label="api: 3 passed, 1 passed on retry, 1 failed"' in html


def test_section_empty():
    """A run with nothing to count has no charts."""
    assert section_html(Tally()) == ""


def test_section_one_folder():
    """With a single folder, only the run's donut shows: a second would repeat it."""
    html = section_html(_tally(_report("a", "passed")))
    assert html.count('class="donut"') == 1


def test_section_folders():
    """One donut for the run, then one per folder, named."""
    html = section_html(
        _tally(_report("a", "passed"), _report("b", "failed", folder="ui_testing"))
    )
    assert html.count('class="donut"') == 3
    assert '<div class="charts__name">ui_testing</div>' in html


def test_legend():
    """The legend always names passed and failed; the others only when they happened."""
    html = section_html(_tally(_report("a", "passed")))
    assert "Passed <strong>1</strong>" in html
    assert "Failed <strong>0</strong>" in html
    assert "Skipped" not in html
