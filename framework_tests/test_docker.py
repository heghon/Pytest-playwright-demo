"""
The Docker image stays on the project's Python version. The Dockerfile has to
state it on its own, since a build can't read .python-version, so this is what
stops the two from drifting apart.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_docker_python():
    """The Dockerfile's PYTHON_VERSION is the one .python-version pins."""
    pinned = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    match = re.search(r"^ARG PYTHON_VERSION=(\S+)$", dockerfile, re.MULTILINE)
    assert match, "The Dockerfile no longer declares ARG PYTHON_VERSION."
    assert match.group(1) == pinned, (
        f"The Dockerfile builds on Python {match.group(1)}, but .python-version "
        f"pins {pinned}: update the ARG PYTHON_VERSION line to match."
    )
