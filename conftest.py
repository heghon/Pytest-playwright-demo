"""
Command-line options for the suite, and the check that runs before anything.

This file exists only because of where pytest looks. Everything else lives in
stepdefs/conftest.py, but pytest_addoption is read while the command line is
still being parsed — before any conftest below the root directory is imported —
so an option declared down there is simply never registered, and pytest rejects
the flag it was supposed to add.

What the option then *does* is in stepdefs/conftest.py, beside the tag handling
it belongs to: see pytest_collection_modifyitems.
"""

import pytest

from utils import venv_check


def pytest_configure(config):
    """
    Refuses to run on a venv that has drifted from requirements.txt.

    Here rather than in stepdefs/conftest.py so it runs first, before a single
    scenario is collected: a run on the wrong versions produces results that
    look perfectly normal and mean something else.
    """
    problems = venv_check.check()
    if problems:
        raise pytest.UsageError(venv_check.message(problems))


def pytest_addoption(parser):
    parser.addoption(
        "--jira",
        default=None,
        metavar="KEY",
        help=(
            "Run only the scenarios tagged with this issue, e.g. --jira JIRA-105. "
            "The JIRA- prefix is optional: --jira 105 means the same thing."
        ),
    )
    parser.addoption(
        "--accessibility",
        action="store_true",
        default=False,
        help=(
            "Check every page the scenarios visit with axe-core, and list the "
            "violations in an Accessibility section at the bottom of the report. "
            "Findings never fail a test."
        ),
    )
    parser.addoption(
        "--history-dir",
        default="report-history",
        metavar="DIR",
        # Written --history-dir=DIR, never with a space: pytest picks its root
        # folder before this file is read, and would take an existing DIR given
        # on its own for a folder of tests.
        help=(
            "Where past reports are archived and compared with, one folder per "
            "set of filters (default: report-history). Write it --history-dir=DIR."
        ),
    )
    parser.addoption(
        "--reset-history",
        action="store_true",
        default=False,
        help=(
            "Empty the report history before this run, which then starts a new "
            "one: nothing to compare with, no past flakiness. Every set of "
            "filters is wiped, not only this run's."
        ),
    )
    parser.addoption(
        "--no-history",
        action="store_true",
        default=False,
        help=(
            "Neither compare this run with earlier ones nor archive it — for runs "
            "that are not part of the story, like python check.py's."
        ),
    )
