"""
Run history: what changed since the last comparable run, and an archive of the
recent reports to go back to.

What changed. Each run is compared with the previous run that selected its tests
the same way — same tag or Jira key, same paths, same engine — and only the
changes are reported, in one line at the top of the report and as an emoji on
the affected rows:

    🔴 regression   passed in the compared run, fails now
    🟢 fix          failed in the compared run, passes now
    🆕 new          not in the compared run at all

A test that stays green, or stays red, is not mentioned: an expected failure
like the checkout scenario would otherwise be reported on every run, and a new
failure would be lost among the old ones. Only tests present in both runs are
compared, so a test a filtered run did not select is never reported as gone.

The archive. Every run is copied to <history>/<key>/<run>/, report and results
together. The newest KEEP runs of each key are kept; all but the newest lose
their videos and traces, by far the heaviest files, and say so in a banner.
Their pages, steps, notes and screenshots stay. <history>/index.html lists them.

Runs also expire after MAX_AGE, whatever their key. The count alone only clears
a key that keeps being run: one used once, say a single Jira issue on Firefox,
would otherwise keep its run forever, and every new combination of filters adds
a key. The price: filters left unused for longer than MAX_AGE have nothing to be
compared with on their next run, which starts their history over.

Locally the history is report-history/, next to reports/. On CI it is the
published site's history/ folder, downloaded before the run and published with
it: see utils/site.py.
"""

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from html import escape
from pathlib import Path

# Runs kept per key. The newest keeps everything; the others are trimmed.
KEEP = 5

# How long an archived run is kept, whatever its key.
MAX_AGE = timedelta(days=7)

# How a run's folder is named: its start time, which sorts in time order.
RUN_ID_FORMAT = "%Y-%m-%dT%H-%M-%SZ"

# What an archived run loses: videos and traces. Screenshots are small and
# worth keeping.
TRIMMED_SUFFIXES = {".webm", ".zip"}

# Marks an index.html that has already been given the archived banner.
_ARCHIVED_MARK = "<!-- archived-report -->"

RESULTS_FILE = "results.json"

# The run in progress, set by pytest_configure in stepdefs/conftest.py. None when
# the run has no history: --no-history, --collect-only, or code imported outside
# a run altogether, like the framework's own unit tests.
CURRENT = None

OK = {"passed"}
KO = {"failed", "error"}

# Worse outcomes win when a test's phases disagree: a passing call followed by a
# teardown error is an error.
_RANK = {"passed": 0, "skipped": 1, "failed": 2, "error": 3}

CHANGES = {
    "regression": (
        "🔴",
        "regression",
        "regressions",
        "Passed in the compared run, fails now",
    ),
    "fixed": ("🟢", "fix", "fixes", "Failed in the compared run, passes now"),
    "new": ("🆕", "new", "new", "Not in the compared run"),
}

# pytest.ini's default -m, which leaves out the smoke scenarios. A run with it,
# and nothing else, is a full run.
_DEFAULT_MARKEXPR = "not smoke"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def run_key(
    markexpr: str = "",
    jira: str = "",
    keyword: str = "",
    paths: tuple[str, ...] = (),
    browsers: tuple[str, ...] = (),
    channel: str = "",
) -> tuple[str, str]:
    """
    The key runs are compared under, and a label to show for it. Two runs share
    a key when they selected their tests the same way, on the same engine.
    """
    selection = []
    markexpr = markexpr.strip()
    if markexpr and markexpr != _DEFAULT_MARKEXPR:
        selection.append(f"tag {markexpr}")
    if jira:
        selection.append(jira)
    if keyword:
        selection.append(f"k {keyword}")
    selection.extend(paths)
    engine = channel or "+".join(browsers or ("chromium",))

    label = " · ".join(selection or ["full run"]) + f" · {engine}"
    key = _slug("-".join(selection or ["all"]) + f"-{engine}")
    return key, label


def merge_outcome(previous: str | None, report) -> str:
    """A test's outcome so far, once this phase's report is taken into account."""
    if report.failed:
        current = "failed" if report.when == "call" else "error"
    elif report.skipped:
        current = "skipped"
    else:
        current = "passed"
    if previous is None:
        return current
    return max(previous, current, key=_RANK.__getitem__)


def compare(baseline: dict, current: dict) -> dict[str, str]:
    """Each test that changed since the baseline, and how. Unchanged ones are left out."""
    changes = {}
    for nodeid, outcome in current.items():
        if nodeid not in baseline:
            changes[nodeid] = "new"
        elif baseline[nodeid] in OK and outcome in KO:
            changes[nodeid] = "regression"
        elif baseline[nodeid] in KO and outcome in OK:
            changes[nodeid] = "fixed"
    return changes


def _counts(changes: dict[str, str]) -> dict[str, int]:
    counts = {change: 0 for change in CHANGES}
    for change in changes.values():
        counts[change] += 1
    return counts


def _when(started: str) -> str:
    """An ISO timestamp as "29 Oct 2026, 14:02 UTC"."""
    try:
        moment = datetime.fromisoformat(started)
    except ValueError:
        return started
    return moment.strftime("%d %b %Y, %H:%M UTC").lstrip("0")


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


@dataclass
class Run:
    """This run: its key, the tests' outcomes, and the run it is compared with."""

    key: str
    label: str
    history: Path
    started: datetime = field(default_factory=lambda: datetime.now(UTC))
    commit: str = ""
    outcomes: dict[str, str] = field(default_factory=dict)
    names: dict[str, str] = field(default_factory=dict)
    # The compared run's results.json, or None when there is none to compare with.
    baseline: dict | None = None

    @property
    def run_id(self) -> str:
        return self.started.strftime(RUN_ID_FORMAT)

    def record(self, report, name: str = "") -> None:
        self.outcomes[report.nodeid] = merge_outcome(
            self.outcomes.get(report.nodeid), report
        )
        if name:
            self.names[report.nodeid] = name

    def change_for(self, report) -> str:
        """The change this test shows so far, "" for none, used for its row."""
        if self.baseline is None:
            return ""
        outcome = merge_outcome(self.outcomes.get(report.nodeid), report)
        before = self.baseline["results"]
        return compare(
            {k: v["outcome"] for k, v in before.items() if k == report.nodeid},
            {report.nodeid: outcome},
        ).get(report.nodeid, "")

    def changes(self) -> dict[str, str]:
        if self.baseline is None:
            return {}
        before = {k: v["outcome"] for k, v in self.baseline["results"].items()}
        return compare(before, self.outcomes)

    def results(self) -> dict:
        """Everything results.json holds: enough for the next run to compare with."""
        return {
            "key": self.key,
            "label": self.label,
            "run_id": self.run_id,
            "started": self.started.isoformat(timespec="seconds"),
            "commit": self.commit,
            "compared_with": self.baseline["run_id"] if self.baseline else None,
            "changes": _counts(self.changes()),
            "results": {
                nodeid: {"outcome": outcome, "name": self.names.get(nodeid, "")}
                for nodeid, outcome in sorted(self.outcomes.items())
            },
        }


def latest_run(history: Path, key: str) -> dict | None:
    """The newest archived results for this key, or None."""
    folder = history / key
    if not folder.is_dir():
        return None
    for run in sorted(folder.iterdir(), reverse=True):
        try:
            return json.loads((run / RESULTS_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return None


# --- the report ----------------------------------------------------------------


def row_icon(change: str) -> str:
    """The emoji a changed test's row starts with, with a tooltip saying why."""
    if change not in CHANGES:
        return ""
    icon, _, _, meaning = CHANGES[change]
    return f'<span class="change change--{change}" title="{escape(meaning)}">{icon}</span> '


def panel_html(run: Run, history_link: str) -> str:
    """The one-line panel at the top of the report."""
    link = (
        f' · <a href="{escape(history_link, quote=True)}" target="_blank" '
        f'rel="noopener">history</a>'
        if history_link
        else ""
    )
    if run.baseline is None:
        text = (
            f"First run with these filters ({escape(run.label)}): nothing to "
            "compare with yet."
        )
    else:
        commit = run.baseline.get("commit")
        compared = _when(run.baseline.get("started", ""))
        if commit:
            compared += f" ({escape(commit)})"
        counts = _counts(run.changes())
        found = [
            f'<span title="{escape(CHANGES[change][3])}">{CHANGES[change][0]} '
            f"{count} {CHANGES[change][1] if count == 1 else CHANGES[change][2]}"
            f"</span>"
            for change, count in counts.items()
            if count
        ]
        text = (
            f"Since the run of {escape(compared)}, same filters: "
            f"{' · '.join(found) if found else 'no change'}"
        )
    return f'<div class="changes">{text}{link}</div>'


# --- the archive ---------------------------------------------------------------

_ARCHIVED_BANNER = (
    _ARCHIVED_MARK + "<style>.artifact--video,.artifact--trace{display:none}"
    ".archived-note{margin:0 0 12px;padding:8px 12px;border-left:4px solid #b0b0b0;"
    "background:#f2f2f2;color:#444;font-size:13px}"
    "@media (prefers-color-scheme:dark){.archived-note{background:#2b2f36;"
    "color:#cfd3d9;border-left-color:#5a5e66}}</style>"
    '<div class="archived-note">Archived report: its videos and traces were '
    "removed to save space. Results, steps, notes and screenshots are as they "
    "were.</div>"
)


def _trim(run_folder: Path) -> None:
    """Removes an archived run's videos and traces, and says so on its page."""
    for file in run_folder.rglob("*"):
        if file.is_file() and file.suffix in TRIMMED_SUFFIXES:
            file.unlink()
    _remove_empty_folders(run_folder)
    page = run_folder / "index.html"
    if not page.is_file():
        return
    html = page.read_text(encoding="utf-8")
    if _ARCHIVED_MARK in html:
        return
    html = re.sub(r"(<body[^>]*>)", r"\1" + _ARCHIVED_BANNER, html, count=1)
    page.write_text(html, encoding="utf-8")


def _remove_empty_folders(root: Path) -> None:
    """
    Removes every empty folder under root, deepest first, so a parent emptied by
    its children going goes too. root itself stays.

    A failing test's artifact folder usually keeps its screenshot when the video
    and trace are trimmed, but not always: a test can fail before there is a page
    to screenshot, or run with --screenshot=off. Its folder would then be left
    behind empty.
    """
    folders = sorted(
        (path for path in root.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for folder in folders:
        if not any(folder.iterdir()):
            folder.rmdir()


def _expired(run_folder: Path, now: datetime) -> bool:
    """Whether a run is older than MAX_AGE. A folder not named by a date is kept."""
    try:
        started = datetime.strptime(run_folder.name, RUN_ID_FORMAT).replace(tzinfo=UTC)
    except ValueError:
        return False
    return now - started > MAX_AGE


def prune(history: Path, keep: int = KEEP, now: datetime | None = None) -> None:
    """
    Per key: drops runs older than MAX_AGE and past the newest `keep`, trims all
    but the newest, and removes a key left with no run at all.
    """
    if not history.is_dir():
        return
    now = now or datetime.now(UTC)
    for key in history.iterdir():
        if not key.is_dir():
            continue
        runs = sorted((r for r in key.iterdir() if r.is_dir()), reverse=True)
        for old in runs[keep:] + [r for r in runs[:keep] if _expired(r, now)]:
            shutil.rmtree(old)
        runs = [r for r in runs[:keep] if r.exists()]
        for older in runs[1:]:
            _trim(older)
        if not runs:
            shutil.rmtree(key)


def archive(report_dir: Path, run: Run) -> Path:
    """Copies this run's report into the history, then prunes and reindexes it."""
    destination = run.history / run.key / run.run_id
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(report_dir, destination)
    prune(run.history)
    write_index(run.history)
    return destination


def write_index(history: Path) -> None:
    """history/index.html: every kept run, grouped by key, newest first."""
    sections = []
    for key in sorted(k for k in history.iterdir() if k.is_dir()):
        rows, label = [], key.name
        for folder in sorted((r for r in key.iterdir() if r.is_dir()), reverse=True):
            try:
                data = json.loads((folder / RESULTS_FILE).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            label = data.get("label", label)
            outcomes = [r["outcome"] for r in data.get("results", {}).values()]
            failed = sum(o in KO for o in outcomes)
            changes = data.get("changes", {})
            moved = " ".join(
                f"{CHANGES[c][0]} {n}" for c, n in changes.items() if n and c in CHANGES
            )
            rows.append(
                f'<tr><td><a href="{escape(key.name)}/{escape(folder.name)}/index.html">'
                f"{escape(_when(data.get('started', folder.name)))}</a></td>"
                f"<td>{escape(data.get('commit', ''))}</td>"
                f"<td>{len(outcomes) - failed} passed, {failed} failed</td>"
                f"<td>{moved}</td></tr>"
            )
        if rows:
            sections.append(
                f"<h2>{escape(label)}</h2><table>"
                "<tr><th>Run</th><th>Commit</th><th>Results</th><th>Changes</th></tr>"
                f"{''.join(rows)}</table>"
            )
    body = "".join(sections) or "<p>No run archived yet.</p>"
    (history / "index.html").write_text(
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Report history</title><style>"
        "body{font-family:Helvetica,Arial,sans-serif;margin:24px;color:#222;"
        "background:#fff}h2{font-size:16px;margin:24px 0 8px}"
        "table{border-collapse:collapse;font-size:14px}"
        "td,th{padding:6px 14px 6px 0;text-align:left;border-bottom:1px solid #e6e6e6}"
        "a{color:#14539a}"
        "@media (prefers-color-scheme:dark){body{background:#1e1f22;color:#cfd3d9}"
        "td,th{border-bottom-color:#3a3d42}a{color:#8ab8e8}}"
        "</style></head><body><h1>Report history</h1>"
        f"<p>The newest {KEEP} runs for each set of filters, from the last "
        f"{MAX_AGE.days} days. All but the newest have had their videos and "
        "traces removed.</p>"
        f"{body}</body></html>",
        encoding="utf-8",
    )
