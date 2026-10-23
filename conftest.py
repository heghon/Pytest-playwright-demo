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
