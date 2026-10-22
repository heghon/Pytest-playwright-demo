"""
The helpers behind the Curtain Call report and the --jira option, in
stepdefs/conftest.py. Each one is tested on its own, with plain values or small
stand-ins for pytest's objects, so none of these tests runs a scenario.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from stepdefs import conftest
from stepdefs.conftest import (
    JIRA_TAG_RE,
    NO_BROWSER,
    _category_of,
    _cell_text,
    _drop_links_column,
    _engine_of,
    _grouping_of,
    _insert_after_test,
    _jira_cell,
    _media_src,
    _normalised_key,
    _publish_base_url,
    _relative_to_report,
    _step_table,
    _steps_extra,
    _trace_extra,
    pytest_bdd_apply_tag,
    pytest_collection_modifyitems,
    report_note,
)

# --- Jira keys ---------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("105", "JIRA-105"),
        ("JIRA-105", "JIRA-105"),
        (" jira-105 ", "JIRA-105"),
    ],
)
def test_key_normalised(raw, expected):
    """--jira accepts the number alone, any case, with stray spaces."""
    assert _normalised_key(raw) == expected


@pytest.mark.parametrize("tag", ["JIRA-1", "JIRA-105"])
def test_tag_is_jira(tag):
    """The tag pattern recognises an issue key."""
    assert JIRA_TAG_RE.match(tag)


@pytest.mark.parametrize("tag", ["jira-105", "JIRA-", "JIRA-12a", "ui", "XJIRA-1"])
def test_tag_not_jira(tag):
    """The tag pattern rejects anything that is not exactly JIRA-<digits>."""
    assert not JIRA_TAG_RE.match(tag)


def test_tag_to_mark():
    """A @JIRA-xxx tag becomes one jira_key mark carrying the key."""

    def scenario():
        pass

    assert pytest_bdd_apply_tag("JIRA-105", scenario) is True
    (mark,) = scenario.pytestmark
    assert (mark.name, mark.args) == ("jira_key", ("JIRA-105",))


def test_tag_passed_on():
    """Any other tag is left for pytest-bdd to handle as usual."""

    def scenario():
        pass

    assert pytest_bdd_apply_tag("ui", scenario) is None
    assert not hasattr(scenario, "pytestmark")


# --- --jira selection --------------------------------------------------------


def _item(*keys):
    """A stand-in for a collected scenario tagged with these keys."""
    marks = [SimpleNamespace(args=(key,)) for key in keys]
    return SimpleNamespace(
        iter_markers=lambda name: marks if name == "jira_key" else []
    )


def _config(jira):
    """A stand-in for pytest's config, with --jira set and deselection recorded."""
    deselected = []
    return SimpleNamespace(
        getoption=lambda name: jira,
        hook=SimpleNamespace(pytest_deselected=lambda items: deselected.extend(items)),
        deselected=deselected,
    )


def test_jira_selects():
    """--jira keeps only the scenarios tagged with that key, deselecting the rest."""
    wanted, other, untagged = _item("JIRA-105"), _item("JIRA-106"), _item()
    items = [wanted, other, untagged]
    config = _config("105")

    pytest_collection_modifyitems(config, items)

    assert items == [wanted]
    assert config.deselected == [other, untagged]


def test_jira_unset():
    """Without --jira, nothing is deselected."""
    items = [_item("JIRA-105"), _item()]
    config = _config(None)

    pytest_collection_modifyitems(config, items)

    assert len(items) == 2
    assert config.deselected == []


def test_jira_unknown():
    """A key nothing is tagged with stops the run and lists the keys that exist."""
    items = [_item("JIRA-106"), _item("JIRA-105")]

    with pytest.raises(pytest.UsageError) as error:
        pytest_collection_modifyitems(_config("999"), items)

    assert str(error.value) == (
        "No scenario is tagged JIRA-999. Tagged in this run: JIRA-105, JIRA-106."
    )


# --- report_note -------------------------------------------------------------


def test_note_outside_step():
    """report_note() outside a step raises rather than silently losing the note."""
    with pytest.raises(RuntimeError, match="inside a Gherkin step"):
        report_note("lost")


def test_note_in_step(monkeypatch):
    """report_note() appends to the running step's notes, as text."""
    step = {"notes": []}
    monkeypatch.setattr(conftest, "_current_step", step)

    report_note("slow response")
    report_note(42)

    assert step["notes"] == ["slow response", "42"]


# --- grouping ----------------------------------------------------------------


@pytest.mark.parametrize(
    "rel_filename, category",
    [
        ("ui_testing/todo.feature", "ui_testing"),
        ("features/automation/login.feature", "automation"),
        ("loose.feature", ""),
    ],
)
def test_category(rel_filename, category):
    """The category is the folder holding the feature file, whatever the prefix."""
    assert _category_of(rel_filename) == category


def test_group_scenario():
    """A scenario is filed under its category folder and its feature."""
    data = {"folder": "api", "feature": "Product catalog API"}
    assert _grouping_of(SimpleNamespace(), data) == ("api", "Product catalog API")


def test_group_plain_test():
    """A test with no Gherkin behind it is filed under its own folder and file."""
    item = SimpleNamespace(path=Path("stepdefs/api/test_extra.py"))
    assert _grouping_of(item, None) == ("api", "test_extra")


def test_group_no_file():
    """Something with no file at all is left ungrouped."""
    assert _grouping_of(SimpleNamespace(), None) == ("", "")


# --- paths and URLs ----------------------------------------------------------


def test_path_inside(tmp_path):
    """A path under the report folder is written relative to it."""
    media = tmp_path / "test-artifacts" / "one" / "video.webm"
    assert _relative_to_report(media, tmp_path) == Path("test-artifacts/one/video.webm")


def test_path_outside(tmp_path):
    """A path outside the report folder stays absolute."""
    report_dir = tmp_path / "reports"
    elsewhere = tmp_path / "elsewhere" / "video.webm"
    assert _relative_to_report(elsewhere, report_dir) == elsewhere.resolve()


def test_media_url(tmp_path):
    """Media under the report gets a relative URL, percent-encoded."""
    media = tmp_path / "test-artifacts" / "a test" / "video.webm"
    assert _media_src(media, tmp_path) == "test-artifacts/a%20test/video.webm"


def test_media_no_url(tmp_path):
    """Media outside the report has no URL the page could use."""
    assert _media_src(tmp_path / "video.webm", tmp_path / "reports") is None


def test_publish_url(monkeypatch):
    """REPORT_BASE_URL is trimmed of spaces and of its trailing slash."""
    monkeypatch.setenv("REPORT_BASE_URL", " https://me.github.io/repo/ ")
    assert _publish_base_url() == "https://me.github.io/repo"


def test_publish_url_unset(monkeypatch):
    """A local run, with no REPORT_BASE_URL, has no publish URL."""
    monkeypatch.delenv("REPORT_BASE_URL", raising=False)
    assert _publish_base_url() == ""


# --- trace command -----------------------------------------------------------


def test_trace_local(tmp_path, monkeypatch):
    """A local trace gets an absolute show-trace command and no viewer link."""
    monkeypatch.delenv("REPORT_BASE_URL", raising=False)
    trace = tmp_path / "test-artifacts" / "one" / "trace.zip"

    content = _trace_extra(trace, tmp_path)["content"]

    assert f"playwright show-trace {trace.resolve()}" in content
    assert "From anywhere" in content
    assert "trace.playwright.dev/?" not in content


def test_trace_published(tmp_path, monkeypatch):
    """A published trace gets a relative command and a link into the viewer."""
    monkeypatch.setenv("REPORT_BASE_URL", "https://me.github.io/repo")
    trace = tmp_path / "test-artifacts" / "one" / "trace.zip"

    content = _trace_extra(trace, tmp_path)["content"]

    assert "playwright show-trace test-artifacts/one/trace.zip" in content
    assert "From the folder holding this report" in content
    # The trace's public URL, percent-encoded into the viewer's query string.
    assert (
        "https://trace.playwright.dev/?trace=https%3A%2F%2Fme.github.io%2Frepo"
        "%2Ftest-artifacts%2Fone%2Ftrace.zip" in content
    )


# --- report cells ------------------------------------------------------------


def test_jira_cell_empty():
    """No keys leaves the Jira cell empty."""
    assert _jira_cell([]) == '<td class="col-jira"></td>'


def test_jira_cell_text(monkeypatch):
    """Without JIRA_BASE_URL the keys show as plain text."""
    monkeypatch.delenv("JIRA_BASE_URL", raising=False)
    assert _jira_cell(["JIRA-1", "JIRA-2"]) == (
        '<td class="col-jira">JIRA-1, JIRA-2</td>'
    )


def test_jira_cell_links(monkeypatch):
    """With JIRA_BASE_URL each key links to its issue, trailing slash or not."""
    monkeypatch.setenv("JIRA_BASE_URL", "https://team.atlassian.net/")
    cell = _jira_cell(["JIRA-1"])
    assert 'href="https://team.atlassian.net/browse/JIRA-1"' in cell
    assert ">JIRA-1</a>" in cell


def test_links_dropped():
    """pytest-html's Links column is removed."""
    cells = ["<th>Result</th>", '<th class="col-links">Links</th>', "<th>Test</th>"]
    _drop_links_column(cells)
    assert cells == ["<th>Result</th>", "<th>Test</th>"]


def test_links_absent():
    """A row with no Links column is left as it was."""
    cells = ["<td>passed</td>", "<td>test</td>"]
    _drop_links_column(cells)
    assert cells == ["<td>passed</td>", "<td>test</td>"]


def test_insert_after():
    """A new column goes straight after the Test column."""
    cells = ["<td>passed</td>", '<td class="col-testId">t</td>', "<td>1s</td>"]
    _insert_after_test(cells, "<td>new</td>")
    assert cells[2] == "<td>new</td>"


def test_insert_last():
    """With no Test column to follow, a new column goes last."""
    cells = ["<td>passed</td>"]
    _insert_after_test(cells, "<td>new</td>")
    assert cells == ["<td>passed</td>", "<td>new</td>"]


def test_cell_text():
    """The text of a cell is what sits between its tags, newlines included."""
    assert _cell_text('<td class="col-testId">a\nb</td>') == "a\nb"


# --- engine column -----------------------------------------------------------


def _engine_item(
    fixturenames=("browser_name",), channel=None, browsers=(), params=None
):
    """A stand-in for a test item, with the options the Engine column reads."""
    options = {"--browser-channel": channel, "--browser": list(browsers)}
    item = SimpleNamespace(
        fixturenames=list(fixturenames),
        config=SimpleNamespace(getoption=lambda name, default=None: options[name]),
    )
    if params is not None:
        item.callspec = SimpleNamespace(params=params)
    return item


def test_engine_none():
    """A test that never asks for a browser reads "no browser"."""
    assert _engine_of(_engine_item(fixturenames=())) == NO_BROWSER


def test_engine_channel():
    """--browser-channel wins over the engine: chrome, not chromium."""
    item = _engine_item(channel="chrome", params={"browser_name": "chromium"})
    assert _engine_of(item) == "chrome"


def test_engine_param():
    """On a multi-engine run, the engine comes from the parametrisation."""
    assert _engine_of(_engine_item(params={"browser_name": "webkit"})) == "webkit"


def test_engine_option():
    """On a single-engine run, the engine comes from --browser."""
    assert _engine_of(_engine_item(browsers=["firefox"])) == "firefox"


def test_engine_default():
    """With nothing said at all, the engine is chromium."""
    assert _engine_of(_engine_item()) == "chromium"


# --- step rendering ----------------------------------------------------------


def test_table_none():
    """A step with no data table renders nothing for it."""
    assert _step_table(None) == ""


def test_table_rows():
    """Every table row renders alike, header included, with cells escaped."""
    html = _step_table([["name", "price"], ["<b>Lamp</b>", "9.99"]])
    assert html.count("<tr>") == 2
    assert "<td>&lt;b&gt;Lamp&lt;/b&gt;</td>" in html


def _step(status, notes=()):
    """A recorded step, as pytest_bdd_before_scenario stores it."""
    return {
        "keyword": "Given",
        "name": "a step",
        "status": status,
        "notes": list(notes),
        "table": None,
    }


def test_steps_status():
    """Each step renders with its status, under the scenario's name."""
    data = {"name": "A scenario", "steps": [_step("passed"), _step("skipped")]}
    content = _steps_extra(data)["content"]
    assert "Scenario: A scenario" in content
    assert 'class="step step--passed"' in content
    assert 'class="step step--skipped"' in content


def test_steps_running():
    """A step still "running" at the end is where the scenario failed."""
    content = _steps_extra({"name": "s", "steps": [_step("running")]})["content"]
    assert 'class="step step--failed"' in content


def test_steps_notes():
    """A step with notes can be folded, counts them, and escapes them."""
    data = {"name": "s", "steps": [_step("passed", notes=["one", "<two>"])]}
    content = _steps_extra(data)["content"]
    assert "step__head--clickable" in content
    assert "2 notes" in content
    assert '<div class="step__note">&lt;two&gt;</div>' in content


def test_steps_no_notes():
    """A step without notes is not clickable."""
    content = _steps_extra({"name": "s", "steps": [_step("passed")]})["content"]
    assert "step__head--clickable" not in content
