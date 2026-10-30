"""
The run history in stepdefs/history.py: filter keys, comparison, the one-line
panel, and the archive with its trimming. Made-up runs on a temporary folder.
"""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from stepdefs.history import (
    KEEP,
    MAX_AGE,
    Run,
    compare,
    latest_run,
    merge_outcome,
    panel_html,
    prune,
    row_icon,
    run_key,
    write_index,
)

# --- filter keys ---------------------------------------------------------------


@pytest.mark.parametrize(
    "options, key, label",
    [
        ({}, "all-chromium", "full run · chromium"),
        ({"markexpr": "not smoke"}, "all-chromium", "full run · chromium"),
        ({"markexpr": "api"}, "tag-api-chromium", "tag api · chromium"),
        ({"jira": "JIRA-105"}, "jira-105-chromium", "JIRA-105 · chromium"),
        ({"browsers": ("firefox",)}, "all-firefox", "full run · firefox"),
        (
            {"browsers": ("chromium",), "channel": "chrome"},
            "all-chrome",
            "full run · chrome",
        ),
        (
            {"paths": ("stepdefs/ui_testing/test_todo_e2e.py",)},
            "stepdefs-ui-testing-test-todo-e2e-py-chromium",
            "stepdefs/ui_testing/test_todo_e2e.py · chromium",
        ),
    ],
)
def test_key(options, key, label):
    """Runs share a key only when they selected the same tests on the same engine."""
    assert run_key(**options) == (key, label)


# --- outcomes and comparison ---------------------------------------------------


def _phase(when, outcome, nodeid="t"):
    """A stand-in for one phase's test report."""
    return SimpleNamespace(
        nodeid=nodeid,
        when=when,
        failed=outcome == "failed",
        skipped=outcome == "skipped",
    )


def test_outcome_call_fails():
    """A failing call makes the test failed."""
    assert merge_outcome("passed", _phase("call", "failed")) == "failed"


def test_outcome_teardown():
    """A teardown failure after a passing call is an error, and wins."""
    assert merge_outcome("passed", _phase("teardown", "failed")) == "error"


def test_outcome_kept():
    """A passing teardown never hides an earlier failure."""
    assert merge_outcome("failed", _phase("teardown", "passed")) == "failed"


def test_compare():
    """Regressions, fixes and new tests are found; unchanged tests are left out."""
    before = {"a": "passed", "b": "failed", "c": "failed", "d": "passed"}
    now = {"a": "failed", "b": "passed", "c": "failed", "d": "passed", "e": "passed"}
    assert compare(before, now) == {"a": "regression", "b": "fixed", "e": "new"}


def test_compare_errors():
    """An error counts as a failure, both ways."""
    assert compare({"a": "passed"}, {"a": "error"}) == {"a": "regression"}
    assert compare({"a": "error"}, {"a": "passed"}) == {"a": "fixed"}


def test_compare_unselected():
    """A test the new run did not select is not reported as gone."""
    assert compare({"a": "passed", "b": "passed"}, {"a": "passed"}) == {}


def test_compare_skipped():
    """A skipped test is neither a regression nor a fix."""
    assert compare({"a": "passed"}, {"a": "skipped"}) == {}


# --- the run and its panel ----------------------------------------------------


def _baseline(**outcomes):
    """A compared run's results.json, as an earlier run would have written it."""
    return {
        "run_id": "2099-01-01T10-00-00Z",
        "started": "2099-01-01T10:00:00+00:00",
        "commit": "abc1234",
        "results": {n: {"outcome": o, "name": ""} for n, o in outcomes.items()},
    }


def _run(tmp_path, baseline=None, **outcomes):
    run = Run("all-chromium", "full run · chromium", tmp_path, baseline=baseline)
    run.outcomes.update(outcomes)
    return run


def test_panel_first(tmp_path):
    """With nothing to compare with, the panel says so."""
    html = panel_html(_run(tmp_path), "")
    assert "First run with these filters (full run · chromium)" in html


def test_panel_counts(tmp_path):
    """Only the kinds of change that happened are counted, in the singular or plural."""
    run = _run(
        tmp_path,
        _baseline(a="passed", b="passed", c="failed"),
        a="failed",
        b="failed",
        c="passed",
    )
    html = panel_html(run, "")
    assert "Since the run of 1 Jan 2099, 10:00 UTC (abc1234), same filters:" in html
    assert "🔴 2 regressions" in html
    assert "🟢 1 fix" in html
    assert "new" not in html


def test_panel_quiet(tmp_path):
    """A run that changed nothing says "no change"."""
    run = _run(tmp_path, _baseline(a="failed"), a="failed")
    assert "same filters: no change" in panel_html(run, "")


def test_panel_link(tmp_path):
    """The panel links to the history when given where it is."""
    html = panel_html(_run(tmp_path), "https://site.test/history/index.html")
    assert 'href="https://site.test/history/index.html"' in html


def test_row_icon():
    """Each change has its emoji; no change has none."""
    assert ">🔴</span>" in row_icon("regression")
    assert ">🟢</span>" in row_icon("fixed")
    assert ">🆕</span>" in row_icon("new")
    assert row_icon("") == ""


def test_change_for(tmp_path):
    """A row knows its own change while the run is still going."""
    run = _run(tmp_path, _baseline(t="passed"))
    assert run.change_for(_phase("call", "failed")) == "regression"
    assert run.change_for(_phase("call", "passed")) == ""


def test_results_file(tmp_path):
    """results.json carries what the next run compares with, and what changed."""
    run = _run(tmp_path, _baseline(a="passed"), a="failed", b="passed")
    data = run.results()
    assert data["compared_with"] == "2099-01-01T10-00-00Z"
    assert data["changes"] == {"regression": 1, "fixed": 0, "new": 1}
    assert data["results"]["a"] == {"outcome": "failed", "name": ""}


# --- the archive ---------------------------------------------------------------


def _archived(history, key, run_id, outcome="passed"):
    """An archived run on disk: page, results, and one of each artifact."""
    folder = history / key / run_id
    artifacts = folder / "test-artifacts" / "t"
    artifacts.mkdir(parents=True)
    for name in ("video.webm", "trace.zip", "test-failed-1.png"):
        (artifacts / name).write_bytes(b"x")
    (folder / "index.html").write_text("<html><body><p>report</p></body></html>")
    (folder / "results.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "label": "full run · chromium",
                "started": "2099-01-01T10:00:00+00:00",
                "commit": "abc1234",
                "changes": {"regression": 1, "fixed": 0, "new": 0},
                "results": {"t": {"outcome": outcome, "name": ""}},
            }
        )
    )
    return folder


def test_latest(tmp_path):
    """The newest archived run of a key is the one compared with."""
    _archived(tmp_path, "k", "2099-01-01T10-00-00Z")
    _archived(tmp_path, "k", "2099-01-02T10-00-00Z", outcome="failed")
    assert latest_run(tmp_path, "k")["run_id"] == "2099-01-02T10-00-00Z"


def test_latest_none(tmp_path):
    """A key never archived has nothing to compare with."""
    assert latest_run(tmp_path, "never-run") is None


def test_latest_unreadable(tmp_path):
    """A newest run with unreadable results falls back on the one before."""
    _archived(tmp_path, "k", "2099-01-01T10-00-00Z")
    broken = _archived(tmp_path, "k", "2099-01-02T10-00-00Z")
    (broken / "results.json").write_text("{not json")
    assert latest_run(tmp_path, "k")["run_id"] == "2099-01-01T10-00-00Z"


# A "now" for the pruning tests, close enough to their made-up runs that age
# only matters where a test says so. Tests that leave it out prune against the
# real clock, which every 2099 run is still in the future of.
NOW = datetime(2099, 1, 10, tzinfo=UTC)


def test_prune_keep(tmp_path):
    """Only the newest KEEP runs of a key stay."""
    for day in range(1, KEEP + 3):
        _archived(tmp_path, "k", f"2099-01-{day:02d}T10-00-00Z")
    prune(tmp_path, now=NOW)
    kept = sorted(p.name for p in (tmp_path / "k").iterdir())
    assert len(kept) == KEEP
    assert kept[0] == "2099-01-03T10-00-00Z"


def test_prune_age(tmp_path):
    """A run older than MAX_AGE goes, however few runs its key has."""
    old = _archived(tmp_path, "k", "2099-01-01T10-00-00Z")
    recent = _archived(tmp_path, "k", "2099-01-09T10-00-00Z")
    prune(tmp_path, now=datetime(2099, 1, 10, tzinfo=UTC))
    assert not old.exists()
    assert recent.exists()


def test_prune_empty_key(tmp_path):
    """A key whose runs all expired disappears from the history."""
    _archived(tmp_path, "used-once", "2099-01-01T10-00-00Z")
    prune(tmp_path, now=datetime(2099, 2, 1, tzinfo=UTC))
    assert not (tmp_path / "used-once").exists()


def test_prune_age_edge(tmp_path):
    """A run exactly MAX_AGE old is still kept; a second more and it goes."""
    run = _archived(tmp_path, "k", "2099-01-01T10-00-00Z")
    started = datetime(2099, 1, 1, 10, tzinfo=UTC)
    prune(tmp_path, now=started + MAX_AGE)
    assert run.exists()
    prune(tmp_path, now=started + MAX_AGE + timedelta(seconds=1))
    assert not run.exists()


def test_prune_odd_name(tmp_path):
    """A folder not named by a date is never expired by mistake."""
    odd = tmp_path / "k" / "not-a-date"
    odd.mkdir(parents=True)
    prune(tmp_path, now=datetime(2199, 1, 1, tzinfo=UTC))
    assert odd.exists()


def test_prune_trim(tmp_path):
    """Older runs lose videos and traces and say so; the newest keeps all."""
    old = _archived(tmp_path, "k", "2099-01-01T10-00-00Z")
    new = _archived(tmp_path, "k", "2099-01-02T10-00-00Z")
    prune(tmp_path)
    old_files = {p.name for p in old.rglob("*") if p.is_file()}
    assert "video.webm" not in old_files and "trace.zip" not in old_files
    assert "test-failed-1.png" in old_files
    assert "Archived report" in (old / "index.html").read_text()
    assert {"video.webm", "trace.zip"} <= {p.name for p in new.rglob("*")}
    assert "Archived report" not in (new / "index.html").read_text()


def test_prune_empty_folders(tmp_path):
    """Folders left empty by trimming go, up to the run; others stay."""
    old = _archived(tmp_path, "k", "2099-01-01T10-00-00Z")
    # A second failing test with no screenshot: only a video and a trace.
    bare = old / "test-artifacts" / "no-screenshot"
    bare.mkdir()
    (bare / "video.webm").write_bytes(b"x")
    (bare / "trace.zip").write_bytes(b"x")
    _archived(tmp_path, "k", "2099-01-02T10-00-00Z")
    prune(tmp_path)
    assert not bare.exists()
    assert (old / "test-artifacts" / "t" / "test-failed-1.png").exists()
    assert old.exists()


def test_prune_empty_artifacts(tmp_path):
    """A run whose only artifacts were trimmed keeps no empty test-artifacts/."""
    old = _archived(tmp_path, "k", "2099-01-01T10-00-00Z")
    (old / "test-artifacts" / "t" / "test-failed-1.png").unlink()
    _archived(tmp_path, "k", "2099-01-02T10-00-00Z")
    prune(tmp_path)
    assert not (old / "test-artifacts").exists()
    assert (old / "index.html").exists()


def test_prune_once(tmp_path):
    """Pruning twice never puts a second banner on a page."""
    old = _archived(tmp_path, "k", "2099-01-01T10-00-00Z")
    _archived(tmp_path, "k", "2099-01-02T10-00-00Z")
    prune(tmp_path)
    prune(tmp_path)
    assert (old / "index.html").read_text().count("Archived report") == 1


def test_index(tmp_path):
    """The history index lists each key's runs, linked, with their changes."""
    _archived(tmp_path, "all-chromium", "2099-01-01T10-00-00Z")
    write_index(tmp_path)
    html = (tmp_path / "index.html").read_text()
    assert "<h2>full run · chromium</h2>" in html
    assert 'href="all-chromium/2099-01-01T10-00-00Z/index.html"' in html
    assert "🔴 1" in html


def test_run_id(tmp_path):
    """A run's folder name is its start time, which sorts in time order."""
    run = Run("k", "l", tmp_path, started=datetime(2099, 1, 2, 3, 4, 5, tzinfo=UTC))
    assert run.run_id == "2099-01-02T03-04-05Z"
