import base64
from html import escape
from pathlib import Path
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


@pytest.fixture(autouse=True)
def _artifacts_dir(request, output_path):
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

# Videos are inlined into the report as base64 data URIs. Safari sandboxes a
# file:// page to its own directory and below, so reports/report.html simply
# cannot follow a link into the sibling test-results/ folder — embedding the
# bytes sidesteps file access entirely. Above this size we fall back to showing
# the path, so a long run can't produce a report too heavy to open.
MAX_EMBED_BYTES = 10 * 1024 * 1024

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


def _screenshot_extra(screenshot: Path, name: str = "Screenshot on failure"):
    """
    Renders the screenshot ourselves rather than via extras.image(), so a plain
    click can open it in a new tab — see _OPEN_IMG_JS. This also leaves
    pytest-html's media viewer with nothing to show, so it hides itself and all
    three artifacts line up in one consistent stack.

    The image is the one --screenshot=only-on-failure already wrote to disk,
    read at teardown alongside the video and the trace. Grabbing our own via the
    page fixture is no longer possible from a hook — see _artifacts_dir.
    """
    try:
        encoded = base64.b64encode(screenshot.read_bytes()).decode("utf-8")
    except Exception:
        return None

    return extras.html(
        f'<div class="artifact artifact--screenshot">'
        f'<div class="artifact__label">{escape(name)}</div>'
        f'<img class="artifact__img" alt="{escape(name)}" '
        f'data-name="{escape(name)}" title="Click to open in a new tab" '
        f'src="data:image/png;base64,{encoded}" '
        f'onclick="{escape(_OPEN_IMG_JS, quote=True)}">'
        f"</div>"
    )


def _video_extra(video: Path):
    """
    Builds an inline <video> player for a Playwright failure recording.
    Returns None if the file can't be read.

    Note: pytest-html's own extras.video() is unusable here — its media viewer
    assigns the source to a <source type="video/mp4"> hardcoded in the template,
    and a browser skips a source whose declared type doesn't match the WebM.
    """
    try:
        size = video.stat().st_size
        if size > MAX_EMBED_BYTES:
            return extras.html(
                f'<div class="artifact artifact--video">'
                f'<div class="artifact__label">Video ({escape(video.name)})</div>'
                f'<div class="artifact__note">Too large to embed '
                f'({size // (1024 * 1024)} MB). Open it from:</div>'
                f'<code class="artifact__cmd">{escape(str(video.resolve()))}</code>'
                f"</div>"
            )
        encoded = base64.b64encode(video.read_bytes()).decode("utf-8")
    except Exception:
        return None

    return extras.html(
        f'<div class="artifact artifact--video">'
        f'<div class="artifact__label">Video ({escape(video.name)})</div>'
        f'<video controls preload="metadata" '
        f'src="data:video/webm;base64,{encoded}"></video>'
        f"</div>"
    )


def _trace_extra(trace: Path):
    """
    A trace is a zip that only means anything inside Playwright's viewer, so
    linking it just triggers a download. Show the command to open it instead,
    ready to copy.
    """
    command = f"playwright show-trace {trace.resolve()}"
    return extras.html(
        f'<div class="artifact artifact--trace">'
        f'<div class="artifact__label">Trace ({escape(trace.name)})</div>'
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


def pytest_html_results_table_header(cells):
    _drop_links_column(cells)


def pytest_html_results_table_row(report, cells):
    _drop_links_column(cells)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()

    # "call" phase: the test body just ran. Only note the verdict here — the
    # artifacts don't exist on disk yet.
    if report.when == "call":
        item.stash[TEST_FAILED] = report.failed

    # "teardown" phase: by now pytest-playwright has finished writing
    # test-failed-1.png / video.webm / trace.zip, so only here can we reach them.
    # pytest-html gathers the extras of every phase into the one row it renders,
    # so hanging all three off the teardown report is fine.
    if report.when == "teardown" and item.stash.get(TEST_FAILED, False):
        folder = item.stash.get(ARTIFACTS_DIR, None)
        if folder is not None and folder.is_dir():
            artifacts = []
            for screenshot in sorted(folder.glob("test-failed-*.png")):
                artifacts.append(_screenshot_extra(screenshot))
            for video in sorted(folder.glob("video*.webm")):
                artifacts.append(_video_extra(video))
            for trace in sorted(folder.glob("trace*.zip")):
                artifacts.append(_trace_extra(trace))
            artifacts = [a for a in artifacts if a is not None]
            if artifacts:
                report.extras = getattr(report, "extras", []) + artifacts