"""
The accessibility check behind --accessibility, and the report section it fills.

Off by default. Switched on, every page a scenario lands on is checked with
axe-core's default rule set (WCAG 2.x A and AA, plus Deque's best practices),
and the violations are listed in an Accessibility section at the bottom of the
report, one foldable entry per page. A finding never fails a test: this is an
audit that reports, not an assertion.

When a page is checked: at the end of every Gherkin step, for each page whose
URL changed since its last check. By the end of the
step, the step has waited for what it expected to see; the check then also waits
for the load, and for the page to stop changing.

Two things that rule cannot see, and accessibility_note(page) can: a page
entered and left within one step, and a page that changes without changing URL
(an open dialog, a list after adding to it). Call it in a step to check the
page there and then, only if necessary.

The colours, per page:
    red     at least one critical or serious violation
    orange  only moderate or minor ones
    green   checked, and nothing found
    grey    a page the check could not run on

A scenario that never opens a page, like the API ones, simply has nothing in
the section.
"""

from dataclasses import dataclass, field
from html import escape

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Error as PlaywrightError

# From worst to mildest, which is also the order the report lists them in.
IMPACTS = ["critical", "serious", "moderate", "minor"]
SEVERE = {"critical", "serious"}

# Long enough for a slow public site to load.
LOAD_TIMEOUT_MS = 10_000

# "Finished loading" means the page has stopped changing: nothing added,
# removed or altered for QUIET_MS. STILL_MAX_MS caps the
# wait for a page that animates forever; it is checked as it stands.
QUIET_MS = 300
STILL_MAX_MS = 3_000

_WAIT_UNTIL_STILL_JS = """
([quiet, max]) => new Promise((resolve) => {
  let timer;
  const done = () => { observer.disconnect(); clearTimeout(timer); clearTimeout(cap); resolve(); };
  const observer = new MutationObserver(() => { clearTimeout(timer); timer = setTimeout(done, quiet); });
  observer.observe(document.documentElement,
    { subtree: true, childList: true, attributes: true, characterData: true });
  timer = setTimeout(done, quiet);
  const cap = setTimeout(done, max);
})
"""

# The pages a scenario's browser context opened, and the URL each was last
# checked at, kept on the test item so they are gone with the scenario.
TRACKED_PAGES = pytest.StashKey[list]()
CHECKED_AT = pytest.StashKey[dict]()


@dataclass
class Violation:
    """One broken rule on one page, with every element it was found on."""

    rule: str
    impact: str
    help: str
    help_url: str
    # Element selector -> its HTML, so checking a page twice lists each once.
    elements: dict[str, str] = field(default_factory=dict)


@dataclass
class PageResult:
    """Everything found on one page, in one engine, across every scenario."""

    url: str
    engine: str
    scenarios: list[str] = field(default_factory=list)
    violations: dict[str, Violation] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    checks: int = 0

    def colour(self) -> str:
        if not self.checks:
            return "grey"
        impacts = {violation.impact for violation in self.violations.values()}
        if impacts & SEVERE:
            return "red"
        return "orange" if impacts else "green"


@dataclass
class Results:
    """The whole run's findings, filled as scenarios go and rendered at the end."""

    enabled: bool = False
    axe_version: str = ""
    pages: dict[tuple[str, str], PageResult] = field(default_factory=dict)

    def page(self, url: str, engine: str, scenario: str) -> PageResult:
        result = self.pages.setdefault((url, engine), PageResult(url, engine))
        if scenario not in result.scenarios:
            result.scenarios.append(scenario)
        return result

    def record(self, url: str, engine: str, scenario: str, response: dict) -> None:
        """Merges one axe-core response into the page it was run on."""
        result = self.page(url, engine, scenario)
        result.checks += 1
        self.axe_version = response.get("testEngine", {}).get("version", "")
        for found in response.get("violations", []):
            violation = result.violations.setdefault(
                found["id"],
                Violation(
                    found["id"],
                    found.get("impact") or "minor",
                    found.get("help", ""),
                    found.get("helpUrl", ""),
                ),
            )
            for node in found.get("nodes", []):
                target = " ".join(str(part) for part in node.get("target", []))
                violation.elements.setdefault(target, node.get("html", ""))

    def record_error(self, url: str, engine: str, scenario: str, error: str) -> None:
        """Notes a page the check could not run on, rather than dropping it."""
        result = self.page(url, engine, scenario)
        if error not in result.errors:
            result.errors.append(error)


RESULTS = Results()

# The scenario running right now, for accessibility_note() to file a check
# under. A module global for the same reason as _current_step in conftest.py:
# pytest runs one scenario at a time per process.
_current = None

_axe = None


def _engine():
    """axe-core's script, read once per run rather than once per page."""
    global _axe
    if _axe is None:
        _axe = Axe()
    return _axe


def _settle(page) -> None:
    """Waits for the page to finish loading, then for it to stop changing."""
    page.wait_for_load_state("load", timeout=LOAD_TIMEOUT_MS)
    page.evaluate(_WAIT_UNTIL_STILL_JS, [QUIET_MS, STILL_MAX_MS])


def check(page, scenario: str, engine: str) -> None:
    """Runs axe-core on the page as it is now, and files what it finds."""
    url = page.url
    try:
        _settle(page)
        response = _engine().run(page).response
    except PlaywrightError as error:
        first_line = str(error).strip().splitlines()[0] if str(error).strip() else ""
        RESULTS.record_error(url, engine, scenario, first_line or type(error).__name__)
        return
    RESULTS.record(url, engine, scenario, response)


def start_scenario(name: str, engine: str) -> None:
    global _current
    _current = {"name": name, "engine": engine}


def end_scenario() -> None:
    global _current
    _current = None


def check_new_pages(node) -> None:
    """Checks every tracked page whose URL changed since its last check."""
    if _current is None:
        return
    checked_at = node.stash.setdefault(CHECKED_AT, {})
    for page in node.stash.get(TRACKED_PAGES, []):
        if page.is_closed() or not page.url.startswith("http"):
            continue
        if checked_at.get(page) == page.url:
            continue
        checked_at[page] = page.url
        check(page, _current["name"], _current["engine"])


def accessibility_note(page) -> None:
    """
    Checks the page now, in the state it is in, and files the findings in the
    report's Accessibility section, for the moments the automatic check cannot
    see: a page passed through within one step, or one that changed without its
    URL changing.

        from stepdefs.accessibility import accessibility_note

        @when("I open the menu")
        def open_menu(inventory_page, page):
            inventory_page.open_menu()
            accessibility_note(page)

    Without --accessibility it does nothing, so it can stay in the steps for
    good. Outside a scenario it raises an issue, like report_note.
    """
    if not RESULTS.enabled:
        return
    if _current is None:
        raise RuntimeError(
            "accessibility_note() has to be called from inside a scenario — "
            "there is no scenario running to file this check under."
        )
    check(page, _current["name"], _current["engine"])


# --- the report section ------------------------------------------------------

_LABELS = {
    "red": "critical or serious issues",
    "orange": "moderate or minor issues only",
    "green": "nothing found",
    "grey": "could not be checked",
}

# Folds the section's entries along with pytest-html's own "Show all details"
# and "Hide all details", which would otherwise leave them as they were. The
# section is built from a <template> once the page has loaded: the summary hook
# that carries this runs above the results table, before the table exists.
_SECTION_JS = """
<script>
(function () {
  function place() {
    var template = document.getElementById('a11y-template');
    if (!template || document.getElementById('a11y')) { return; }
    document.body.appendChild(template.content.cloneNode(true));
    [['show_all_details', true], ['hide_all_details', false]].forEach(function (pair) {
      var button = document.getElementById(pair[0]);
      if (!button) { return; }
      button.addEventListener('click', function () {
        document.querySelectorAll('#a11y details').forEach(function (d) { d.open = pair[1]; });
      });
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', place);
  } else {
    place();
  }
})();
</script>
"""


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


HTML_PREVIEW_CHARS = 160
ELEMENTS_SHOWN = 10


def _one_line(html: str) -> str:
    """Markup on a single line, cut to HTML_PREVIEW_CHARS."""
    flat = " ".join(html.split())
    if len(flat) <= HTML_PREVIEW_CHARS:
        return flat
    return f"{flat[:HTML_PREVIEW_CHARS]}…"


def _rule_html(violation: Violation) -> str:
    shown = list(violation.elements.items())[:ELEMENTS_SHOWN]
    elements = "".join(
        f'<li><code class="a11y__target">{escape(target)}</code>'
        f'<code class="a11y__html">{escape(_one_line(html))}</code></li>'
        for target, html in shown
    )
    hidden = len(violation.elements) - len(shown)
    if hidden:
        elements += f'<li class="a11y__more">…and {hidden} more</li>'
    link = (
        f' <a href="{escape(violation.help_url, quote=True)}" target="_blank" '
        f'rel="noopener">how to fix</a>'
        if violation.help_url
        else ""
    )
    return (
        f'<div class="a11y__rule">'
        f'<div class="a11y__rule-head">'
        f'<span class="a11y__impact a11y__impact--{escape(violation.impact)}">'
        f"{escape(violation.impact)}</span> "
        f'<span class="a11y__rule-id">{escape(violation.rule)}</span> '
        f"{escape(violation.help)} "
        f'<span class="a11y__count">{_plural(len(violation.elements), "element")}</span>'
        f"{link}"
        f"</div>"
        f'<ul class="a11y__elements">{elements}</ul>'
        f"</div>"
    )


def _page_html(result: PageResult) -> str:
    colour = result.colour()
    rules = sorted(
        result.violations.values(),
        key=lambda violation: (IMPACTS.index(violation.impact), violation.rule),
    )
    if rules:
        elements = sum(len(violation.elements) for violation in rules)
        tally = f"{_plural(len(rules), 'rule')} broken, {_plural(elements, 'element')}"
    elif result.checks:
        tally = "no violations"
    else:
        tally = "could not be checked"
    errors = "".join(
        f'<div class="a11y__error">Could not check: {escape(error)}</div>'
        for error in result.errors
    )
    scenarios = ", ".join(escape(name) for name in result.scenarios)
    return (
        f'<details class="a11y__page a11y--{colour}">'
        f'<summary><span class="a11y__dot" title="{_LABELS[colour]}"></span>'
        f'<span class="a11y__url">{escape(result.url)}</span>'
        f'<span class="a11y__engine">{escape(result.engine)}</span>'
        f'<span class="a11y__count">{tally}</span></summary>'
        f'<div class="a11y__scenarios">Checked by: {scenarios}</div>'
        f"{errors}"
        f"{''.join(_rule_html(violation) for violation in rules)}"
        f"</details>"
    )


def section_html(results: Results) -> str:
    """The Accessibility section, or nothing at all when the check was off."""
    if not results.enabled:
        return ""

    pages = sorted(
        results.pages.values(),
        key=lambda result: (
            ["red", "orange", "green", "grey"].index(result.colour()),
            result.url,
            result.engine,
        ),
    )
    counts = {colour: 0 for colour in _LABELS}
    for result in pages:
        counts[result.colour()] += 1

    engine = (
        f"axe-core {escape(results.axe_version)}" if results.axe_version else "axe-core"
    )
    legend = " · ".join(
        f'<span class="a11y__legend a11y--{colour}"><span class="a11y__dot"></span>'
        f"{counts[colour]} {label}</span>"
        for colour, label in _LABELS.items()
        if colour != "grey"
    )
    body = "".join(_page_html(result) for result in pages)
    if not body:
        body = '<p class="a11y__summary">No scenario in this run opened a page.</p>'

    return (
        f'<template id="a11y-template"><section id="a11y" class="a11y">'
        f'<h2 class="a11y__title">Accessibility</h2>'
        f'<p class="a11y__summary">{_plural(len(pages), "page")} checked with '
        f"{engine}, default rules (WCAG A and AA, and best practices). Findings "
        f"never fail a test.</p>"
        f'<p class="a11y__summary">{legend}</p>'
        f"{body}"
        f"</section></template>{_SECTION_JS}"
    )
