"""
Command-line options for the suite.

This file exists only because of where pytest looks. Everything else lives in
stepdefs/conftest.py, but pytest_addoption is read while the command line is
still being parsed — before any conftest below the root directory is imported —
so an option declared down there is simply never registered, and pytest rejects
the flag it was supposed to add.

What the option then *does* is in stepdefs/conftest.py, beside the tag handling
it belongs to: see pytest_collection_modifyitems.
"""


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
