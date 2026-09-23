import os
from html import escape
from pathlib import Path
from urllib.parse import quote, urlencode
import pytest
from dotenv import load_dotenv
from pytest_html import extras
from pytest_metadata.plugin import metadata_key
import re

load_dotenv()

JIRA_TAG_RE = re.compile(r"^JIRA-\d+$")


@pytest.hookimpl(trylast=True)
def pytest_configure(config):
    """
    Drops the Environment rows that would render blank, and only those.

    pytest-base-url publishes a "Base URL" row unconditionally: with no base URL
    configured it falls back to the base_url ini value, which defaults to "" and
    not to None, while its own guard only rules out None. Set one — here, or via
    --base-url — and the row keeps its value like any other.

    trylast so the plugins filling the metadata have had their turn; pytest-html
    only snapshots the table at session start, so this still lands in time.
    """
    metadata = config.stash.get(metadata_key, None)
    if metadata is None:
        return
    for key, value in list(metadata.items()):
        if value is None or (isinstance(value, str) and not value.strip()):
            del metadata[key]

# Where pytest-playwright will drop this test's artifacts, and whether the test
# body failed. Both are recorded while the test is still alive, because
# pytest_runtest_makereport can no longer discover either one on its own —
# see _artifacts_dir below.
ARTIFACTS_DIR = pytest.StashKey[Path]()
TEST_FAILED = pytest.StashKey[bool]()


# Failure videos are recorded at half the viewport, rather than
# pytest-playwright's default of the viewport scaled to fit 800x800. Linking the
# media already keeps the report itself small whatever happens; this just keeps
# the artifacts folder from growing faster than it needs to.
VIDEO_SCALE = 0.5


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """
    Shrinks the recording, deriving the size from whatever viewport is in play
    instead of pinning a landscape one. A --device run then records its phone in
    portrait at the right aspect ratio, rather than squeezed into a 16:9 box —
    and a device added later needs no change here. The tests still *run* at the
    full viewport; only the recording is smaller.
    """
    # Window-sized, so there's no viewport to scale from — leave it to Playwright.
    if browser_context_args.get("no_viewport"):
        return browser_context_args

    # Only present when --device supplied one; otherwise Playwright's own default.
    viewport = browser_context_args.get("viewport") or {"width": 1280, "height": 720}

    def scaled(value: int) -> int:
        # Even numbers only — video encoders are happier with them.
        return max(2, round(value * VIDEO_SCALE / 2) * 2)

    return {
        **browser_context_args,
        "record_video_size": {
            "width": scaled(viewport["width"]),
            "height": scaled(viewport["height"]),
        },
    }


@pytest.fixture(autouse=True)
def _artifacts_dir(request, output_path, browser_name):
    """
    Pins pytest-playwright's per-test output folder onto the item.

    The teardown hook used to read it back from item.funcargs, but funcargs only
    ever holds fixtures pytest resolved during setup: the ones in the test's
    signature plus the autouse ones. Our steps pull "page" lazily, mid-test, via
    pytest-bdd — so neither "page" nor the "output_path" behind it was ever
    filled in there, and the hook silently found nothing to attach.

    Requesting output_path from an autouse fixture puts it in the closure for
    every test. It only joins --output with a slug of the node id, so it starts
    no browser and costs nothing for the non-Playwright tests.

    browser_name is here for the same reason, and it is load-bearing:
    pytest-playwright only parameterises a test across engines when it finds
    browser_name in the fixture closure, and a pytest-bdd scenario never
    mentions it. Without this, `--browser firefox` was accepted and ignored —
    every run quietly went to chromium.
    """
    request.node.stash[ARTIFACTS_DIR] = Path(output_path)


def pytest_bdd_apply_tag(tag, function):
    # Gherkin tags become pytest marks by default — cute for @ui,
    # chaotic once we have fifty @JIRA-xxx tags. JIRA keys get rerouted
    # into one shared "jira_key" mark so pytest.ini doesn't turn into a JIRA export.
    if JIRA_TAG_RE.match(tag):
        pytest.mark.jira_key(tag)(function)
        return True
    return None


def _normalised_key(raw: str) -> str:
    key = raw.strip().upper()
    return key if key.startswith("JIRA-") else f"JIRA-{key}"


def pytest_collection_modifyitems(config, items):
    """
    Implements --jira, because -m cannot. The flag itself is declared in the
    root conftest.py, which is the only place pytest reads options from.

    pytest_bdd_apply_tag above funnels every @JIRA-xxx tag into one jira_key
    mark and keeps the issue itself as the mark's *argument*. That is what stops
    pytest.ini becoming a JIRA export, but -m only ever matches a mark's name:
    "-m JIRA-105" matches nothing at all, and "-m jira_key" matches every tagged
    scenario in the suite. Reading the arguments back at collection time is the
    only way to select one issue.
    """
    requested = config.getoption("--jira")
    if not requested:
        return

    wanted = _normalised_key(requested)
    selected, deselected = [], []
    for item in items:
        selected.append(item) if wanted in _jira_keys_of(item) else deselected.append(item)

    if not selected:
        # Better than "no tests ran": the likeliest cause is a typo, and the
        # answer to it is the list of keys that do exist.
        known = sorted({key for item in items for key in _jira_keys_of(item)})
        raise pytest.UsageError(
            f"No scenario is tagged {wanted}. "
            f"Tagged in this run: {', '.join(known) if known else 'none'}."
        )

    config.hook.pytest_deselected(items=deselected)
    items[:] = selected


# The Gherkin behind a test, recorded as it runs so the report can show the
# scenario rather than the generated function name pytest-bdd derives from it.
# Steps start out "skipped" and are marked as they execute, so whatever the run
# never reached is visible as exactly that.
SCENARIO = pytest.StashKey[dict]()

# The step running right now, for report_note() to hang an observation on.
#
# A module global rather than a fixture, so a note can be imported and called
# where it is needed instead of being threaded through the signature of every
# step that might want one. Safe because pytest runs a single scenario at a time
# per process — an xdist worker is its own process, with its own copy of this.
_current_step = None


def _scenario_data(node):
    return node.stash.get(SCENARIO, None)


def report_note(message):
    """
    Records an observation against the step currently running, for something
    worth reporting that isn't worth failing the run over — a slow response, a
    cosmetic glitch, a value that looked off. The scenario still passes; the
    note simply shows up under its step in the report.

        from stepdefs.conftest import report_note

        @given("I am logged in to SauceDemo", target_fixture="inventory_page")
        def logged_in(logged_in_inventory_page):
            report_note("needed a second attempt")
            return logged_in_inventory_page

    A note only means something attached to a step, so calling it outside one
    raises rather than quietly dropping what you wanted recorded.
    """
    if _current_step is None:
        raise RuntimeError(
            "report_note() has to be called from inside a Gherkin step — "
            "there is no step running to attach this to."
        )
    _current_step["notes"].append(str(message))


def _category_of(rel_filename) -> str:
    """
    The folder a feature file lives in, or "" for one sitting loose in the
    features directory — the report then simply has nothing to group it under
    rather than inventing a category for it.

    Read as "the directory holding the file" rather than by position, because
    what rel_filename is relative to is not fixed: pytest-bdd hands over
    "ui_testing/todo.feature" here, while its own parser builds the same path
    with the features directory still on the front.
    """
    return Path(rel_filename).parent.name


def pytest_bdd_before_scenario(request, feature, scenario):
    request.node.stash[SCENARIO] = {
        "name": scenario.name,
        "feature": feature.name,
        # The category folder the feature file sits in, for the report's outer
        # grouping. rel_filename is "features/automation/login.feature", so the
        # first part is the base directory and the last is the file itself.
        "folder": _category_of(feature.rel_filename),
        "current": None,
        "steps": [
            {
                "keyword": step.keyword,
                "name": step.name,
                "line": step.line_number,
                "status": "skipped",
                "notes": [],
                # The Gherkin table under a step, if it has one. The step name
                # alone reads "I fill in my checkout information:" and tells you
                # nothing about what was actually filled in.
                "table": (
                    [[cell.value for cell in row.cells] for row in step.datatable.rows]
                    if step.datatable
                    else None
                ),
            }
            for step in scenario.steps
        ],
    }


def pytest_bdd_before_step(request, feature, scenario, step, step_func):
    global _current_step
    _current_step = None
    data = _scenario_data(request.node)
    if data is None:
        return
    # Matched on line number rather than a running counter: it is unique within
    # a feature file and survives a scenario outline rendering its steps anew.
    for recorded in data["steps"]:
        if recorded["line"] == step.line_number and recorded["status"] == "skipped":
            recorded["status"] = "running"
            data["current"] = recorded
            _current_step = recorded
            return


def pytest_bdd_after_step(request, feature, scenario, step, step_func, step_func_args):
    global _current_step
    data = _scenario_data(request.node)
    if data and data["current"] is not None:
        data["current"]["status"] = "passed"
        data["current"] = None
    _current_step = None


def pytest_bdd_step_error(
    request, feature, scenario, step, step_func, step_func_args, exception
):
    global _current_step
    data = _scenario_data(request.node)
    if data and data["current"] is not None:
        data["current"]["status"] = "failed"
        data["current"] = None
    _current_step = None



# Screenshots and videos are linked, never inlined as base64.
#
# Inlining used to be the only option: Safari sandboxes a file:// page to its own
# directory and below, and the report could not reach a sibling folder. --output
# now drops the artifacts *under* the report, so an ordinary relative URL reaches
# them everywhere — locally, in the downloaded bundle, and on Pages.
#
# Linking keeps the report a fixed size however many tests fail, and lets the
# browser fetch each video only when someone presses play. That matters more than
# it sounds: pytest-html packs the whole report into a single JSON blob that
# JavaScript has to parse on load, and a string over ~512 MB cannot be parsed at
# all — a report full of inlined video could reach a size that simply won't open.
# The trade is that reports/index.html is no longer one file you can email on its
# own; send the folder.

# Playwright's hosted viewer. It's a static page: a trace opened here is read in
# the browser, not uploaded, so it's safe to point at a local file.
TRACE_VIEWER_URL = "https://trace.playwright.dev/"


def _publish_base_url() -> str:
    """
    Where this run is being published, or "" for an ordinary local run.

    Set by the CI workflow. A published report has to be readable from any
    machine; a local one is only ever read on the machine that wrote it, which
    is why the trace command below can afford to be an absolute path there.
    """
    return os.getenv("REPORT_BASE_URL", "").strip().rstrip("/")


def _report_dir(config) -> Path:
    """The folder the HTML report is written into — everything else hangs off it."""
    return Path(config.getoption("htmlpath")).resolve().parent


def _relative_to_report(path: Path, report_dir: Path) -> Path:
    """
    Path as written from the report's own folder, or absolute if it lies outside.

    One rule for every path in the report, which is what lets --output put the
    artifacts under reports/: the same string then works locally, inside the
    downloaded bundle, and on Pages, because in all three the media sits at the
    same place relative to the report.
    """
    resolved = path.resolve()
    try:
        return resolved.relative_to(report_dir)
    except ValueError:
        return resolved


def _media_src(media: Path, report_dir: Path) -> str | None:
    """
    A relative URL for the media, or None when it sits outside the report's own
    folder — pointed there by an --output that overrides pytest.ini — and so no
    relative URL can reach it from the page.
    """
    location = _relative_to_report(media, report_dir)
    if location.is_absolute():
        return None
    return quote(location.as_posix())

# Inline handler for the "Copy" button next to the trace command.
# It has to be an onclick attribute: pytest-html injects HTML extras with
# insertAdjacentHTML, which runs inline handlers but never executes <script>
# tags. navigator.clipboard is undefined on file:// in Safari (not a secure
# context), hence the execCommand fallback.
_COPY_JS = (
    "(function(btn){"
    "var cmd=btn.parentElement.querySelector('.artifact__cmd').textContent;"
    "var done=function(ok){btn.textContent=ok?'Copied!':'Copy failed';"
    "setTimeout(function(){btn.textContent='Copy';},1500);};"
    "var legacy=function(){"
    "var ta=document.createElement('textarea');ta.value=cmd;"
    "ta.style.position='fixed';ta.style.opacity='0';"
    "document.body.appendChild(ta);ta.select();"
    "var ok=false;try{ok=document.execCommand('copy');}catch(e){}"
    "document.body.removeChild(ta);done(ok);};"
    "if(navigator.clipboard&&navigator.clipboard.writeText){"
    "navigator.clipboard.writeText(cmd).then(function(){done(true);},legacy);"
    "}else{legacy();}"
    "})(this)"
)

# Opens the screenshot in a new tab. It has to build the tab's content by hand:
# every browser blocks top-level navigation to a data: URL, so pytest-html's own
# window.open(dataUri) just lands on about:blank. Writing an <img> into a blank
# window we opened ourselves is allowed. Single quotes only — this string ends up
# inside an HTML attribute.
_OPEN_IMG_JS = (
    "(function(img){"
    "var w=window.open('','_blank');if(!w){return;}"
    "var d=w.document;"
    "if(!d.body){d.write('<body></body>');d.close();}"
    "d.title=img.getAttribute('data-name')||'Screenshot';"
    "d.body.style.margin='0';"
    "d.body.style.background='#1e1f22';"
    "d.body.style.textAlign='center';"
    "var i=d.createElement('img');i.src=img.src;i.style.maxWidth='100%';"
    "d.body.appendChild(i);"
    "})(this)"
)


# Folds a step's notes away and back. Inline like the handlers above, for the
# same reason: pytest-html injects extras with insertAdjacentHTML, which honours
# an inline handler but never runs a <script>. The class goes on the <li>, so the
# caret and the notes can both react to it in CSS alone. Single quotes only —
# this string ends up inside an HTML attribute.
_TOGGLE_NOTES_JS = "(function(h){h.parentElement.classList.toggle('is-collapsed');})(this)"


def _step_table(table):
    """
    The Gherkin table under a step, verbatim.

    Every row is rendered the same. Whether the first one is a header is the
    step definition's business — check_overview_items reads it as data, while
    fill_checkout_info treats it as column names — so the report shows what the
    feature file says and leaves the interpretation alone.
    """
    if not table:
        return ""
    body = "".join(
        "<tr>" + "".join(f"<td>{escape(cell)}</td>" for cell in row) + "</tr>"
        for row in table
    )
    return f'<table class="step__table">{body}</table>'


def _steps_extra(data: dict):
    """
    The scenario as Gherkin, attached whether it passed or failed.

    A failing run stops at a step and leaves the rest untouched, which the
    statuses show on their own — so no traceback here. The reason lives in the
    log pytest-html already prints, and in the screenshot, video and trace below.
    """
    rows = []
    for step in data["steps"]:
        # Anything still "running" never reached after_step or step_error: the
        # step is where the run came apart, whatever pytest-bdd made of it.
        status = "failed" if step["status"] == "running" else step["status"]
        notes = "".join(
            f'<div class="step__note">{escape(n)}</div>' for n in step["notes"]
        )

        # Only a step that actually has notes becomes clickable, so clicking one
        # without any does nothing rather than looking broken. Notes start
        # visible; the toggle is there for the step that collected a pile of them.
        count = len(step["notes"])
        if count:
            head = (
                f'<div class="step__head step__head--clickable" '
                f'title="Show or hide these notes" '
                f'onclick="{escape(_TOGGLE_NOTES_JS, quote=True)}">'
            )
            toggle = (
                f'<span class="step__toggle">{count} '
                f'note{"s" if count > 1 else ""}</span>'
            )
        else:
            head = '<div class="step__head">'
            toggle = ""

        rows.append(
            f'<li class="step step--{status}">'
            f"{head}"
            f'<span class="step__keyword">{escape(step["keyword"])}</span> '
            f'<span class="step__name">{escape(step["name"])}</span>'
            f"{toggle}"
            f"</div>"
            f"{_step_table(step['table'])}"
            f"{notes}"
            f"</li>"
        )

    return extras.html(
        f'<div class="artifact artifact--steps">'
        f'<div class="artifact__label">Scenario: {escape(data["name"])}</div>'
        f'<ol class="steps">{"".join(rows)}</ol>'
        f"</div>"
    )


def _unreachable_extra(media: Path, report_dir: Path, kind: str, css: str):
    """
    Stands in for media the page has no way to address, which now only happens
    when --output is pointed outside reports/. Shows the absolute path rather
    than dropping the artifact silently.
    """
    return extras.html(
        f'<div class="artifact artifact--{css}">'
        f'<div class="artifact__label">{escape(kind)} ({escape(media.name)})</div>'
        f'<div class="artifact__note">Written outside the report folder, so the '
        f"page can't show it inline. Open it from:</div>"
        f'<code class="artifact__cmd">{escape(str(media.resolve()))}</code>'
        f"</div>"
    )


def _screenshot_extra(screenshot: Path, report_dir: Path, name: str = "Screenshot on failure"):
    """
    Renders the screenshot ourselves rather than via extras.image(), so a plain
    click can open it in a new tab — see _OPEN_IMG_JS. This also leaves
    pytest-html's media viewer with nothing to show, so it hides itself and all
    three artifacts line up in one consistent stack.

    The image is the one --screenshot=only-on-failure already wrote to disk,
    read at teardown alongside the video and the trace. Grabbing our own via the
    page fixture is no longer possible from a hook — see _artifacts_dir.
    """
    src = _media_src(screenshot, report_dir)
    if src is None:
        return _unreachable_extra(screenshot, report_dir, "Screenshot", "screenshot")

    return extras.html(
        f'<div class="artifact artifact--screenshot">'
        f'<div class="artifact__label">{escape(name)}</div>'
        f'<img class="artifact__img" alt="{escape(name)}" '
        f'data-name="{escape(name)}" title="Click to open in a new tab" '
        f'src="{escape(src, quote=True)}" '
        f'onclick="{escape(_OPEN_IMG_JS, quote=True)}">'
        f"</div>"
    )


def _video_extra(video: Path, report_dir: Path):
    """
    Builds an inline <video> player for a Playwright failure recording.

    preload="metadata" is what makes the linked case cheap: the browser fetches
    a few bytes of header per video and the rest only once someone hits play, so
    a report with a hundred failures still opens instantly.

    Note: pytest-html's own extras.video() is unusable here — its media viewer
    assigns the source to a <source type="video/mp4"> hardcoded in the template,
    and a browser skips a source whose declared type doesn't match the WebM.
    """
    src = _media_src(video, report_dir)
    if src is None:
        return _unreachable_extra(video, report_dir, "Video", "video")

    return extras.html(
        f'<div class="artifact artifact--video">'
        f'<div class="artifact__label">Video ({escape(video.name)})</div>'
        f'<video controls preload="metadata" '
        f'src="{escape(src, quote=True)}"></video>'
        f"</div>"
    )


def _trace_extra(trace: Path, report_dir: Path):
    """
    A trace is a zip that only means anything inside Playwright's viewer, so
    linking it just triggers a download. Show the command to open it instead,
    ready to copy.

    Which path depends on who will read it. A published report travels, so an
    absolute path is useless there — on CI it names a runner that no longer
    exists, which is why the command used to come back "does not exist"; the
    relative one resolves inside the bundle and on Pages alike. A local report
    never leaves the machine that wrote it, so it gets the absolute path and you
    can paste the command into any terminal without minding the directory.

    Published runs also get a one-click link into the hosted viewer, built from
    REPORT_BASE_URL, and then nobody has to touch a terminal at all.
    """
    base_url = _publish_base_url()
    location = _relative_to_report(trace, report_dir)

    link = ""
    if base_url and not location.is_absolute():
        trace_url = f"{base_url}/{quote(location.as_posix())}"
        viewer_url = f"{TRACE_VIEWER_URL}?{urlencode({'trace': trace_url})}"
        link = (
            f'<a class="artifact__link" target="_blank" rel="noopener" '
            f'href="{escape(viewer_url, quote=True)}">Open in the trace viewer</a>'
        )
        where = "From the folder holding this report"
    else:
        location = trace.resolve()
        where = "From anywhere"

    command = f"playwright show-trace {location}"

    return extras.html(
        f'<div class="artifact artifact--trace">'
        f'<div class="artifact__label">Trace ({escape(trace.name)})</div>'
        f"{link}"
        f'<div class="artifact__note">{where} — or drop the file '
        f"onto trace.playwright.dev, which never uploads it anywhere:</div>"
        f'<code class="artifact__cmd">{escape(command)}</code>'
        f'<button type="button" class="artifact__copy" '
        f'onclick="{escape(_COPY_JS, quote=True)}">Copy</button>'
        f"</div>"
    )


def _drop_links_column(cells):
    """
    Removes pytest-html's "Links" column. Every artifact is now rendered inline
    in the expanded row, so the column is always empty. Both hooks below mutate
    the list in place, and pytest-html pairs row cells with header cells by
    index — so the two must always be dropped together.
    """
    for index, cell in enumerate(cells):
        if "col-links" in str(cell) or ">Links<" in str(cell):
            del cells[index]
            return


def pytest_html_report_title(report):
    # Anything beats "report.html", which is just the filename pytest-html falls
    # back to. The cast returns for the curtain call once the performance is
    # over — and "call" is the pytest phase that decides the verdict.
    # One string feeds both the browser tab and the <h1>, so it stays short.
    report.title = "Curtain Call"


# What the Engine column says for a test that runs no browser at all. Styled
# down in the stylesheet so it reads as an answer rather than as a result.
NO_BROWSER = "no browser"


def _engine_of(item):
    """
    Which engine ran this test, or NO_BROWSER for one that never opened a page.

    The channel wins when there is one: --browser-channel chrome still reports a
    browser_name of "chromium", and "chrome" is the more useful answer. Falls
    back to --browser for a run with a single engine, where pytest-playwright
    never parameterises and so there is no callspec to read.

    An API test has no browser_name in its closure — see the override in
    stepdefs/api/conftest.py — so naming an engine for it would be an untruth.
    An empty cell would only raise the question; the label answers it.
    """
    if "browser_name" not in item.fixturenames:
        return NO_BROWSER

    channel = item.config.getoption("--browser-channel", None)
    if channel:
        return channel
    callspec = getattr(item, "callspec", None)
    if callspec:
        name = callspec.params.get("browser_name")
        if name:
            return name
    chosen = item.config.getoption("--browser", None) or []
    return chosen[0] if chosen else "chromium"


def _insert_after_test(cells, cell):
    """
    Puts a cell straight after Test, in the header and in every row alike.

    pytest-html pairs the two by index — _hydrate_data looks up
    table_header[index] to decide whether a cell is sortable — so the header and
    the rows have to agree on where the column sits, which is why both hooks
    below go through here.

    Callers insert Engine first and Jira second, which lands them as
    Test | Jira | Engine: the ticket belongs next to the scenario it covers,
    and the engine is a detail of the run rather than of the test.
    """
    for index, existing in enumerate(cells):
        if "col-testId" in str(existing) or 'data-column-type="testId"' in str(existing):
            cells.insert(index + 1, cell)
            return
    cells.append(cell)


def _jira_keys_of(item):
    """
    The issue keys behind a scenario, from the @JIRA-xxx tags in its feature file.

    pytest_bdd_apply_tag has already funnelled those tags into one jira_key
    mark, so this only has to read them back off the item.
    """
    return [mark.args[0] for mark in item.iter_markers("jira_key") if mark.args]


def _jira_cell(keys):
    """
    The issue keys, linked when JIRA_BASE_URL says where the site lives.

    Without it the keys still show as plain text: a local run with no Jira
    configured should look the same, minus the links.
    """
    if not keys:
        return '<td class="col-jira"></td>'

    base_url = os.getenv("JIRA_BASE_URL", "").strip().rstrip("/")
    if base_url:
        rendered = ", ".join(
            f'<a href="{escape(f"{base_url}/browse/{quote(key)}", quote=True)}" '
            f'target="_blank" rel="noopener">{escape(key)}</a>'
            for key in keys
        )
    else:
        rendered = escape(", ".join(keys))
    return f'<td class="col-jira">{rendered}</td>'


def pytest_html_results_table_header(cells):
    _drop_links_column(cells)
    _insert_after_test(
        cells, '<th class="sortable" data-column-type="engine">Engine</th>'
    )
    _insert_after_test(
        cells, '<th class="sortable" data-column-type="jira">Jira</th>'
    )


def _grouping_of(item, data):
    """
    The two headings a result is filed under in the report: its category folder
    and the feature it belongs to.

    A scenario takes both from its feature file. Anything else — a plain pytest
    test added later, or a collection error — falls back to its own file, so a
    test that never went near Gherkin still lands somewhere sensible instead of
    in a nameless group.
    """
    if data is not None:
        return data["folder"], data["feature"] or ""

    path = getattr(item, "path", None)
    if path is None:
        return "", ""
    return path.parent.name, path.stem


def _rewrite_test_cell(report, cells):
    """
    Puts the Gherkin scenario in the Test column, and tags the cell with the
    feature it came from.

    pytest-bdd names the generated function after the scenario, so the node id
    reads test_scrape_book_listings_to_csv (example), a name that exists nowhere in the
    feature file you wrote. The scenario itself is what you recognise, so it
    goes in the column, with the node id kept as the cell's tooltip for when you
    need to find or rerun the thing.

    The two data attributes are what _GROUPING_JS groups the table on, and this
    is the only cell guaranteed to be in every row — the Jira and Engine cells
    can both legitimately be empty.
    """
    title = getattr(report, "scenario_name", None)
    folder = getattr(report, "group_folder", "")
    feature = getattr(report, "group_feature", "")
    for index, cell in enumerate(cells):
        if "col-testId" in str(cell):
            # A test with no scenario behind it keeps whatever pytest-html put
            # in the cell; only the grouping is added.
            label = escape(title) if title else _cell_text(str(cell))
            cells[index] = (
                f'<td class="col-testId" title="{escape(report.nodeid, quote=True)}" '
                f'data-folder="{escape(folder, quote=True)}" '
                f'data-feature="{escape(feature, quote=True)}">'
                f"{label}</td>"
            )
            return


def _cell_text(cell: str) -> str:
    match = re.search(r"<td[^>]*>(.*)</td>", cell, re.S)
    return match.group(1) if match else cell


def pytest_html_results_table_row(report, cells):
    _drop_links_column(cells)
    _rewrite_test_cell(report, cells)
    engine = getattr(report, "engine", "")
    engine_class = "col-engine col-engine--none" if engine == NO_BROWSER else "col-engine"
    _insert_after_test(cells, f'<td class="{engine_class}">{escape(engine)}</td>')
    _insert_after_test(cells, _jira_cell(getattr(report, "jira_keys", [])))


def pytest_html_results_table_html(report, data):
    """
    Drops the "No log output captured." placeholder.

    pytest-html falls back to that line whenever a test produced no output,
    which for a passing scenario is every time — an empty box saying there is
    nothing to show. Emptying the list removes the log element outright rather
    than leaving a blank one: app.js only builds it `if (log)`.

    Matched on the exact placeholder, so a test that really did log something
    keeps it, pass or fail.
    """
    if data == ["No log output captured."]:
        del data[:]


# Regroups the results table under two foldable headings: the category folder a
# feature file lives in, then the feature itself. Both come from the data
# attributes _rewrite_test_cell puts on the Test cell, so a new folder or a new
# feature file groups itself with nothing to register here.
#
# It has to be JavaScript rather than markup. pytest-html builds the table from
# a JSON blob at load time and rebuilds it from scratch on every sort, filter
# and expand — any <tbody> inserted from Python would be discarded by the first
# click. So the grouping re-runs after each rebuild, watching for the moment
# app.js swaps the table out.
#
# It travels in pytest_html_results_summary because that is the one hook whose
# HTML is written into the page itself: a <script> there is parsed with the
# document and runs before app.js, in time to catch even the first render.
_GROUPING_JS = """
<script>
(function () {
  var STORE = 'collapsedReportGroups';

  function read() {
    try { return new Set(JSON.parse(sessionStorage.getItem(STORE)) || []); }
    catch (e) { return new Set(); }
  }

  /* Which groups are folded is kept in sessionStorage, the way pytest-html
     already keeps its sort and its collapsed rows — so folding survives a
     sort, a filter, and a reload of the page. */
  var collapsed = read();

  /* Every heading seen so far, so "Hide all details" can fold the ones a
     filter is currently keeping off the table as well as the ones on it. */
  var known = new Set();

  function save() {
    try { sessionStorage.setItem(STORE, JSON.stringify(Array.from(collapsed))); }
    catch (e) {}
  }

  function counts(bodies) {
    var bad = bodies.filter(function (body) {
      return body.classList.contains('failed') || body.classList.contains('error');
    }).length;
    return {
      total: bodies.length + (bodies.length === 1 ? ' test' : ' tests'),
      bad: bad,
    };
  }

  function heading(kind, key, name, bodies) {
    var columns = document.querySelectorAll('#results-table-head th').length || 1;
    var tally = counts(bodies);
    var tbody = document.createElement('tbody');
    tbody.className = 'group group--' + kind;
    tbody.dataset.groupKey = key;
    known.add(key);
    tbody.innerHTML =
      '<tr><td colspan="' + columns + '">' +
        '<span class="group__caret"></span>' +
        '<span class="group__name"></span>' +
        '<span class="group__count">' + tally.total + '</span>' +
        (tally.bad ? '<span class="group__failed">' + tally.bad + ' failed</span>' : '') +
      '</td></tr>';
    /* textContent rather than innerHTML: a feature is named in a .feature file,
       which is not ours to trust as markup. */
    tbody.querySelector('.group__name').textContent = name;
    tbody.addEventListener('click', function () {
      if (collapsed.has(key)) { collapsed.delete(key); } else { collapsed.add(key); }
      save();
      apply();
    });
    return tbody;
  }

  function apply() {
    var table = document.getElementById('results-table');
    if (!table) { return; }
    Array.prototype.forEach.call(table.tBodies, function (body) {
      if (body.classList.contains('group')) {
        body.classList.toggle('is-collapsed', collapsed.has(body.dataset.groupKey));
        /* A feature heading disappears with the folder it belongs to. */
        body.classList.toggle('is-hidden-row',
          !!body.dataset.parentKey && collapsed.has(body.dataset.parentKey));
      } else if (body.dataset.featureKey) {
        body.classList.toggle('is-hidden-row',
          collapsed.has(body.dataset.featureKey) || collapsed.has(body.dataset.folderKey));
      }
    });
  }

  function build(table) {
    if (!table || table.dataset.grouped) { return; }
    table.dataset.grouped = '1';

    var bodies = Array.prototype.filter.call(table.tBodies, function (body) {
      return body.querySelector('.col-testId');
    });
    if (!bodies.length) { return; }

    /* Bucketed in the order the rows already have, so whatever column the
       table is sorted on still decides the order inside each feature. */
    var folders = new Map();
    bodies.forEach(function (body) {
      var cell = body.querySelector('.col-testId');
      var folder = cell.dataset.folder || '';
      var feature = cell.dataset.feature || '';
      body.dataset.folderKey = folder ? 'folder:' + folder : '';
      body.dataset.featureKey = 'folder:' + folder + '/' + feature;
      if (!folders.has(folder)) { folders.set(folder, new Map()); }
      var features = folders.get(folder);
      if (!features.has(feature)) { features.set(feature, []); }
      features.get(feature).push(body);
    });

    var fragment = document.createDocumentFragment();
    folders.forEach(function (features, folder) {
      var folderKey = 'folder:' + folder;
      var everything = [];
      features.forEach(function (list) { everything = everything.concat(list); });
      /* A feature file sitting loose in the features directory has no folder to
         file it under, so its own heading becomes the top level. */
      if (folder) {
        fragment.appendChild(heading('folder', folderKey, folder, everything));
      }
      features.forEach(function (list, feature) {
        var head = heading('feature', folderKey + '/' + feature, feature, list);
        if (folder) { head.dataset.parentKey = folderKey; }
        fragment.appendChild(head);
        list.forEach(function (body) { fragment.appendChild(body); });
      });
    });
    /* The rows are already children of the table, so this reorders them in
       place rather than cloning anything — their click handlers come along. */
    table.appendChild(fragment);
    apply();
  }

  /* "Show all details" and "Hide all details" read as "open everything" and
     "close everything", so they fold the headings too rather than leaving two
     levels of the table untouched. pytest-html binds its own handler to these
     later; both run, and its redraw lands on the state set here. */
  function foldEverything(folded) {
    if (folded) {
      known.forEach(function (key) { collapsed.add(key); });
    } else {
      collapsed.clear();
    }
    save();
    apply();
  }

  [['show_all_details', false], ['hide_all_details', true]].forEach(function (pair) {
    var button = document.getElementById(pair[0]);
    if (button) {
      button.addEventListener('click', function () { foldEverything(pair[1]); });
    }
  });

  var regroup = function () { build(document.getElementById('results-table')); };

  /* app.js replaces the whole table on every redraw, which shows up as a child
     change on <body>. Watching childList only, and never touching <body>
     ourselves, means our own reordering cannot set this off again. */
  new MutationObserver(regroup).observe(document.body, { childList: true });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', regroup);
  } else {
    regroup();
  }
})();
</script>
"""


def pytest_html_results_summary(postfix):
    postfix.append(_GROUPING_JS)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()

    # The table-row hook is handed the report, never the item, so anything it
    # needs has to travel on the report itself.
    data = _scenario_data(item)
    if data is not None:
        report.scenario_name = data["name"]
    report.group_folder, report.group_feature = _grouping_of(item, data)
    report.engine = _engine_of(item)
    report.jira_keys = _jira_keys_of(item)

    # "call" phase: the test body just ran. Only note the verdict here — the
    # artifacts don't exist on disk yet.
    if report.when == "call":
        item.stash[TEST_FAILED] = report.failed

    # "teardown" phase: by now pytest-playwright has finished writing
    # test-failed-1.png / video.webm / trace.zip, so only here can we reach them.
    # pytest-html gathers the extras of every phase into the one row it renders,
    # so hanging all three off the teardown report is fine.
    if report.when == "teardown":
        artifacts = []
        report_dir = _report_dir(item.config)

        # The steps go in whatever the outcome: a passing scenario is worth
        # reading too, and it is the only place a report_note can show up.
        if data is not None:
            artifacts.append(_steps_extra(data))

        folder = item.stash.get(ARTIFACTS_DIR, None)
        if item.stash.get(TEST_FAILED, False) and folder is not None and folder.is_dir():
            for screenshot in sorted(folder.glob("test-failed-*.png")):
                artifacts.append(_screenshot_extra(screenshot, report_dir))
            for video in sorted(folder.glob("video*.webm")):
                artifacts.append(_video_extra(video, report_dir))
            for trace in sorted(folder.glob("trace*.zip")):
                artifacts.append(_trace_extra(trace, report_dir))

        artifacts = [a for a in artifacts if a is not None]
        if artifacts:
            report.extras = getattr(report, "extras", []) + artifacts