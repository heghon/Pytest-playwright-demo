"""
Every quality gate of the project, in one command:

    python check.py

Runs them in order and stops at the first that fails, showing its output. CI
runs this same file, so a green run here means a green quality job there: there
is no second list of checks to fall out of step with this one.

None of the gates needs the network or a browser. Every pytest run here writes
its report under check-reports/, so a check never overwrites the real report in
reports/ —> the root pytest.ini writes one on any run, --collect-only included.
"""

import subprocess
import sys
from pathlib import Path

from utils import venv_check

ROOT = Path(__file__).resolve().parent
REPORTS = ROOT / "check-reports"
SMOKE_REPORT = REPORTS / "smoke" / "index.html"

# What only the report hooks in stepdefs/conftest.py write into a report, and
# none of which is in the stylesheet that --self-contained-html inlines into the
# same file: the feature name (the grouping), the class pair on a passed step
# (the step recording), and the wording of a report_note (the notes).
SMOKE_REPORT_MUST_SHOW = [
    "Framework smoke check",
    "step step--passed",
    "Matches api/schemas/product.schema.json",
]


def _run(*args):
    """Runs a tool from the active venv. Returns whether it passed, and its output."""
    result = subprocess.run(
        [sys.executable, "-m", *args],
        # A failing gate is an answer, not an error: the return code is read below.
        check=False,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.returncode == 0, result.stdout + result.stderr


def _last_line(output):
    """The last non-empty line, where pytest puts its "N passed" summary."""
    lines = [line for line in output.splitlines() if line.strip()]
    return lines[-1].strip("= ") if lines else ""


def venv():
    """The venv matches requirements.txt, so every gate judges the pinned versions."""
    problems = venv_check.check()
    if problems:
        return False, venv_check.message(problems)
    return True, "matches requirements.txt"


def lint():
    """Ruff finds nothing to report."""
    passed, output = _run("ruff", "check", ".")
    return passed, output if not passed else "no findings"


def format_():
    """Every file is laid out the way ruff format writes it."""
    passed, output = _run("ruff", "format", "--check", ".")
    if not passed:
        output += "\nRun 'ruff format .' to fix it."
    return passed, output if not passed else _last_line(output)


def unit():
    """The framework's own unit tests pass."""
    passed, output = _run("pytest", "framework_tests", "-q")
    return passed, output if not passed else _last_line(output)


def collect():
    """Every scenario in the suite is collected: features parse, steps match."""
    passed, output = _run(
        "pytest", "--collect-only", "-q", f"--html={REPORTS / 'collect.html'}"
    )
    return passed, output if not passed else _last_line(output)


def smoke():
    """The @smoke scenarios pass, and the report hooks render them."""
    passed, output = _run(
        "pytest",
        "-m",
        "smoke",
        f"--html={SMOKE_REPORT}",
        f"--output={SMOKE_REPORT.parent / 'test-artifacts'}",
    )
    if not passed:
        return False, output

    # A green run only says the scenarios passed. Whether the hooks still turned
    # them into the report everyone reads is a separate question, and a bump to
    # pytest-html could break that without failing a single test.
    report = SMOKE_REPORT.read_text(encoding="utf-8")
    missing = [text for text in SMOKE_REPORT_MUST_SHOW if text not in report]
    if missing:
        return False, (
            f"The scenarios passed, but {SMOKE_REPORT.relative_to(ROOT)} doesn't show "
            f"{', '.join(repr(text) for text in missing)}: the report hooks in "
            "stepdefs/conftest.py no longer render it."
        )
    return True, f"{_last_line(output)}, report rendered"


GATES = [
    ("venv", venv),
    ("lint", lint),
    ("format", format_),
    ("unit tests", unit),
    ("collect", collect),
    ("smoke", smoke),
]


def main():
    for name, gate in GATES:
        passed, detail = gate()
        if not passed:
            print(f"✘ {name:<11} {gate.__doc__}\n\n{detail.rstrip()}\n")
            print(f"Stopped at the '{name}' gate.")
            return 1
        print(f"✔ {name:<11} {detail}")
    print("✅ All quality gates passed ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
