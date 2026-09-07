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
            report_dir = _report_dir(item.config)
            for screenshot in sorted(folder.glob("test-failed-*.png")):
                artifacts.append(_screenshot_extra(screenshot, report_dir))
            for video in sorted(folder.glob("video*.webm")):
                artifacts.append(_video_extra(video, report_dir))
            for trace in sorted(folder.glob("trace*.zip")):
                artifacts.append(_trace_extra(trace, report_dir))
            artifacts = [a for a in artifacts if a is not None]
            if artifacts:
                report.extras = getattr(report, "extras", []) + artifacts