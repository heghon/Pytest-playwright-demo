"""
The round charts at the top of the report: how many tests passed, for the whole
run and for each folder of features/, readable before anything else on the page.

One donut for the run, then one per folder (api, ui_testing...), every segment in the same order:

    passed            passed on the first attempt
    passed on retry   failed once, passed on retry (see --reruns in pytest.ini)
    failed            failed or errored, retry included
    skipped           skipped

Colour never says it alone: the legend names each segment with its count, the
centre gives the passes, and every segment has a tooltip. The colours themselves
are in assets/report_dark.css, one set per theme.
"""

import math
from dataclasses import dataclass, field
from html import escape

from stepdefs import history

# Segment order, and the label each one goes by.
SEGMENTS = {
    "passed": "Passed",
    "retried": "Passed on retry",
    "failed": "Failed",
    "skipped": "Skipped",
}

# Donut sizes in px: the run's, then each folder's.
RUN_SIZE, RUN_STROKE = 120, 14
FOLDER_SIZE, FOLDER_STROKE = 84, 10

# Room left between two segments, in px along the ring.
GAP = 2


@dataclass
class Tally:
    """Each test's folder and final outcome, filled as the run goes."""

    tests: dict[str, dict] = field(default_factory=dict)

    def record(self, report) -> None:
        if report.outcome == "rerun":
            # A failed attempt with a retry to come: the retry has the say.
            return
        test = self.tests.setdefault(
            report.nodeid, {"folder": "", "outcome": None, "retry": ""}
        )
        test["folder"] = getattr(report, "group_folder", "") or test["folder"]
        test["outcome"] = history.merge_outcome(test["outcome"], report)
        test["retry"] = getattr(report, "retry", "") or test["retry"]

    def counts(self, folder: str | None = None) -> dict[str, int]:
        """How many tests fall in each segment, for one folder or the whole run."""
        counts = dict.fromkeys(SEGMENTS, 0)
        for test in self.tests.values():
            if folder is None or test["folder"] == folder:
                counts[_segment(test)] += 1
        return counts

    def folders(self) -> list[str]:
        """The folders, in the order their first test ran."""
        return list(dict.fromkeys(test["folder"] for test in self.tests.values()))


TALLY = Tally()


def _segment(test: dict) -> str:
    if test["outcome"] in history.KO:
        return "failed"
    if test["outcome"] == "skipped":
        return "skipped"
    return "retried" if test["retry"] == "passed" else "passed"


def _passes(counts: dict[str, int]) -> int:
    return counts["passed"] + counts["retried"]


def donut(counts: dict[str, int], size: int, stroke: int, name: str) -> str:
    """
    One donut as inline SVG: a circle per segment, each drawn as a dash along
    the same ring and pushed round by the segments before it, from 12 o'clock.
    """
    total = sum(counts.values())
    radius = (size - stroke) / 2
    ring = 2 * math.pi * radius
    present = [(key, count) for key, count in counts.items() if count]
    gap = GAP if len(present) > 1 else 0

    circles, start = [], 0.0
    for key, count in present:
        length = ring * count / total
        tip = f"{name} · {SEGMENTS[key]}: {count} of {total}"
        circles.append(
            f'<circle class="donut__seg donut__seg--{key}" cx="{size / 2}" '
            f'cy="{size / 2}" r="{radius:.2f}" stroke-width="{stroke}" '
            f'stroke-dasharray="{max(length - gap, 0.5):.2f} {ring:.2f}" '
            f'stroke-dashoffset="{-start:.2f}"><title>{escape(tip)}</title></circle>'
        )
        start += length

    passes = _passes(counts)
    summary = ", ".join(f"{count} {SEGMENTS[key].lower()}" for key, count in present)
    return (
        f'<div class="donut" style="width:{size}px;height:{size}px">'
        f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" '
        f'role="img" aria-label="{escape(f"{name}: {summary}", quote=True)}">'
        f'<g transform="rotate(-90 {size / 2} {size / 2})">{"".join(circles)}</g>'
        f"</svg>"
        f'<div class="donut__centre"><span class="donut__figure">'
        f'{passes}/{total}</span><span class="donut__unit">passed</span></div>'
        f"</div>"
    )


def _legend(counts: dict[str, int]) -> str:
    """The segments, named and counted for the whole run. Passed and failed
    always show, the other two only when the run had any."""
    items = [
        f'<span class="charts__key"><span class="charts__swatch '
        f'charts__swatch--{key}"></span>{escape(label)} <strong>{counts[key]}</strong>'
        f"</span>"
        for key, label in SEGMENTS.items()
        if counts[key] or key in ("passed", "failed")
    ]
    return f'<div class="charts__legend">{"".join(items)}</div>'


# Moves the charts to right under the report's title, above the Environment
# table: they are what most readers came for. The summary hook only places HTML
# under "Summary", further down. Runs as the page is parsed, the title being
# already there.
_TO_THE_TOP_JS = (
    "<script>(function(){var c=document.currentScript.previousElementSibling,"
    "t=document.getElementById('title');if(c&&t){t.after(c);}})();</script>"
)


def section_html(tally: Tally) -> str:
    """The charts, or "" for a run with no test to count."""
    if not tally.tests:
        return ""
    overall = tally.counts()
    run = (
        f'<div class="charts__run">'
        f"{donut(overall, RUN_SIZE, RUN_STROKE, 'All tests')}"
        f'<div class="charts__name">All tests</div></div>'
    )
    folders = tally.folders()
    # A single folder's donut would only repeat the run's.
    per_folder = ""
    if len(folders) > 1:
        per_folder = "".join(
            f'<div class="charts__folder">'
            f"{donut(tally.counts(f), FOLDER_SIZE, FOLDER_STROKE, f or 'Other')}"
            f'<div class="charts__name">{escape(f or "Other")}</div></div>'
            for f in folders
        )
    return (
        f'<div class="charts">{_legend(overall)}'
        f'<div class="charts__row">{run}{per_folder}</div></div>'
        f"{_TO_THE_TOP_JS}"
    )
