"""
Run history: what changed since the last comparable run, which tests are flaky,
and an archive of the recent reports to go back to.

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

Which tests are flaky?  A test is flaky when its outcome keeps flipping between
pass and fail: one flip is a regression or a fix, FLAKY_FLIPS or more is
instability. Every archived run counts, whatever its filters — a full run and a
tag run both contain the tests they share — plus this run. The mark is added to
whatever else the row shows, pass or fail:

    🎲 flaky        flipped FLAKY_FLIPS times or more in its recent runs

Flips between two runs on the same commit are the strongest evidence, since the
code did not change and the result did; the tooltip says how many there were.
The window is the history's, so a hint rather than a proof: a quick break and
fix reads as two flips too.

The archive. Every run is copied to <history>/<key>/<run>/, report and results
together. <history>/index.html lists the runs that still have a report. Per key,
from the newest:

    the newest run                    full report: videos, traces, the lot
    up to KEEP, within REPORT_MAX_AGE trimmed report: no videos or traces
    beyond either                     results.json only, a few KB
    older than RESULTS_MAX_AGE        deleted

Reports go after a week: they are what weighs. Results stay a month, because
they are what flakiness is measured on.
Both limits apply whatever the key: the count alone only clears a key that
keeps being run, and every new combination of filters adds one. The price:
filters unused for longer than REPORT_MAX_AGE have no report to look back at,
though their next run is still compared with their last results; past
RESULTS_MAX_AGE, there is nothing left and their history starts over.

Locally the history is report-history/, next to reports/. On CI it is the
published site's history/ folder, downloaded before the run and published with
it: see utils/site.py.
"""

import itertools
import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from html import escape
from pathlib import Path

# Runs per key that keep a report. The newest keeps everything; the others are
# trimmed.
KEEP = 5

# How long an archived run keeps its report, and then its results, whatever its
# key.
REPORT_MAX_AGE = timedelta(days=7)
RESULTS_MAX_AGE = timedelta(days=30)

# Pass-fail flips from which a test counts as flaky. One flip is a change.
FLAKY_FLIPS = 2

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

FLAKY_ICON = "🎲"

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


# --- flakiness -----------------------------------------------------------------


@dataclass
class Flakiness:
    """How unsettled a test's recent outcomes have been."""

    flips: int
    runs: int
    same_code: int

    @property
    def flaky(self) -> bool:
        return self.flips >= FLAKY_FLIPS

    def describe(self) -> str:
        """The evidence, as the 🎲 tooltip gives it."""
        times = "time" if self.flips == 1 else "times"
        text = (
            f"Flaky: changed outcome {self.flips} {times} in its last {self.runs} runs"
        )
        if self.same_code:
            text += f", {self.same_code} of them on the same code"
        return text + "."


def flakiness(observations: list[tuple[str, str, str]]) -> Flakiness:
    """
    Counts the pass-fail flips in a test's outcomes, (started, outcome, commit)
    in time order. Skipped runs say nothing either way and are left out.
    """
    seen = [
        (outcome in KO, commit)
        for _, outcome, commit in observations
        if outcome in OK | KO
    ]
    flips = same_code = 0
    for (failed, commit), (failed_next, commit_next) in itertools.pairwise(seen):
        if failed != failed_next:
            flips += 1
            if commit and commit == commit_next:
                same_code += 1
    return Flakiness(flips, len(seen), same_code)


def load_observations(history: Path) -> dict[str, list[tuple[str, str, str]]]:
    """Every archived outcome of every test, all keys together, oldest first."""
    observations: dict[str, list[tuple[str, str, str]]] = {}
    for path in sorted(history.glob(f"*/*/{RESULTS_FILE}")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        started, commit = data.get("started", ""), data.get("commit", "")
        for nodeid, result in data.get("results", {}).items():
            observations.setdefault(nodeid, []).append(
                (started, result.get("outcome", ""), commit)
            )
    for outcomes in observations.values():
        outcomes.sort(key=lambda observation: observation[0])
    return observations


# --- the run -------------------------------------------------------------------


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
    """This run: its key, the tests' outcomes, and what they are measured against."""

    key: str
    label: str
    history: Path
    started: datetime = field(default_factory=lambda: datetime.now(UTC))
    commit: str = ""
    outcomes: dict[str, str] = field(default_factory=dict)
    names: dict[str, str] = field(default_factory=dict)
    # The compared run's results.json, or None when there is none to compare with.
    baseline: dict | None = None
    # Every archived outcome of each test, for flakiness: see load_observations.
    observations: dict[str, list[tuple[str, str, str]]] = field(default_factory=dict)

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

    def flakiness_of(self, nodeid: str, outcome: str) -> Flakiness:
        """A test's flakiness, its archived outcomes and this run's together."""
        now = (self.started.isoformat(timespec="seconds"), outcome, self.commit)
        return flakiness([*self.observations.get(nodeid, []), now])

    def flaky_for(self, report) -> str:
        """The 🎲 tooltip for this test so far, "" when it is not flaky."""
        outcome = merge_outcome(self.outcomes.get(report.nodeid), report)
        found = self.flakiness_of(report.nodeid, outcome)
        return found.describe() if found.flaky else ""

    def flaky(self) -> dict[str, Flakiness]:
        """Every test of this run that is flaky, with its evidence."""
        found = {
            nodeid: self.flakiness_of(nodeid, outcome)
            for nodeid, outcome in self.outcomes.items()
        }
        return {nodeid: f for nodeid, f in found.items() if f.flaky}

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
            "flaky": sorted(self.flaky()),
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


def row_icon(change: str, flaky: str = "") -> str:
    """
    The emoji a test's row starts with: its change, if any, then 🎲 when it is
    flaky — added to the change, never instead of it. Each with a tooltip.
    """
    icons = ""
    if change in CHANGES:
        icon, _, _, meaning = CHANGES[change]
        icons += f'<span class="change change--{change}" title="{escape(meaning)}">{icon}</span>'
    if flaky:
        icons += f'<span class="change change--flaky" title="{escape(flaky)}">{FLAKY_ICON}</span>'
    return f"{icons} " if icons else ""


def panel_html(run: Run, history_link: str) -> str:
    """The one-line panel at the top of the report."""
    link = (
        f' · <a href="{escape(history_link, quote=True)}" target="_blank" '
        f'rel="noopener">history</a>'
        if history_link
        else ""
    )
    flaky = len(run.flaky())
    flaky_note = (
        f'<span title="Outcome flipped {FLAKY_FLIPS} times or more in its recent '
        f'runs">{FLAKY_ICON} {flaky} flaky</span>'
        if flaky
        else ""
    )
    if run.baseline is None:
        text = (
            f"First run with these filters ({escape(run.label)}): nothing to "
            "compare with yet."
        )
        if flaky_note:
            text += f" · {flaky_note}"
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
        if flaky_note:
            found.append(flaky_note)
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


def _strip_to_results(run_folder: Path) -> None:
    """Removes an archived run's whole report, keeping only its results.json."""
    for path in run_folder.iterdir():
        if path.name == RESULTS_FILE:
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


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


def _age(run_folder: Path, now: datetime) -> timedelta | None:
    """How old a run is, from its folder's name. None for a folder not named by a date."""
    try:
        started = datetime.strptime(run_folder.name, RUN_ID_FORMAT).replace(tzinfo=UTC)
    except ValueError:
        return None
    return now - started


def prune(history: Path, keep: int = KEEP, now: datetime | None = None) -> None:
    """
    Applies the retention described at the top of this module, key by key, and
    removes a key left with no run at all. A folder not named by a date is never
    touched: nothing says how old it is.
    """
    if not history.is_dir():
        return
    now = now or datetime.now(UTC)
    for key in history.iterdir():
        if not key.is_dir():
            continue
        runs = sorted((r for r in key.iterdir() if r.is_dir()), reverse=True)
        for position, run in enumerate(runs):
            age = _age(run, now)
            if age is None:
                continue
            if age > RESULTS_MAX_AGE:
                shutil.rmtree(run)
            elif position >= keep or age > REPORT_MAX_AGE:
                _strip_to_results(run)
            elif position > 0:
                _trim(run)
        if not any(key.iterdir()):
            shutil.rmtree(key)


def reset(history: Path) -> None:
    """
    Empties the history, for --reset-history: every key, every run, the index.
    The folder itself stays, so the run that asked starts the new history in it.
    """
    if history.is_dir():
        shutil.rmtree(history)
    history.mkdir(parents=True)


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
    """history/index.html: every run that still has a report, by key, newest first."""
    sections = []
    for key in sorted(k for k in history.iterdir() if k.is_dir()):
        rows, label = [], key.name
        for folder in sorted((r for r in key.iterdir() if r.is_dir()), reverse=True):
            if not (folder / "index.html").is_file():
                continue
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
            flaky = len(data.get("flaky", []))
            rows.append(
                f'<tr><td><a href="{escape(key.name)}/{escape(folder.name)}/index.html">'
                f"{escape(_when(data.get('started', folder.name)))}</a></td>"
                f"<td>{escape(data.get('commit', ''))}</td>"
                f"<td>{len(outcomes) - failed} passed, {failed} failed</td>"
                f"<td>{moved}</td>"
                f"<td>{f'{FLAKY_ICON} {flaky}' if flaky else ''}</td></tr>"
            )
        if rows:
            sections.append(
                f"<h2>{escape(label)}</h2><table>"
                "<tr><th>Run</th><th>Commit</th><th>Results</th><th>Changes</th>"
                "<th>Flaky</th></tr>"
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
        f"{REPORT_MAX_AGE.days} days. All but the newest have had their videos and "
        f"traces removed. Older runs keep only their results, for "
        f"{RESULTS_MAX_AGE.days} days, to tell which tests are flaky.</p>"
        f"{body}</body></html>",
        encoding="utf-8",
    )
