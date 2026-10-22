"""
The monthly maintenance issue's logic, in utils/maintenance.py.

The real script fetches the release data live on every run. These tests feed it
made-up data instead, so they never touch the network and can cover cases no
real Python is in today. The versions are fictional on purpose (Python 9.x):
none of this is a record of actual releases.
"""

from utils.maintenance import (
    dependency_section,
    issue_body,
    latest_patches,
    python_section,
)

# A made-up release cycle, shaped like peps.python.org/api/release-cycle.json,
# with one branch in each support status.
CYCLE = {
    "9.4": {
        "status": "feature",
        "first_release": "2099-10-01",
        "end_of_life": "2104-10",
    },
    "9.3": {
        "status": "bugfix",
        "first_release": "2098-10-01",
        "end_of_life": "2103-10",
    },
    "9.2": {
        "status": "bugfix",
        "first_release": "2097-10-01",
        "end_of_life": "2102-10",
    },
    "9.1": {
        "status": "security",
        "first_release": "2096-10-01",
        "end_of_life": "2101-10",
    },
    "9.0": {
        "status": "end-of-life",
        "first_release": "2095-10-01",
        "end_of_life": "2100-10",
    },
}


def test_patches_latest():
    """The newest stable release per branch wins: 9.2.10 over 9.2.9."""
    manifest = [
        {"version": "9.2.9", "stable": True},
        {"version": "9.2.10", "stable": True},
        {"version": "9.3.0rc1", "stable": False},
        {"version": "9.3.1", "stable": True},
    ]
    assert latest_patches(manifest) == {"9.2": "9.2.10", "9.3": "9.3.1"}


def test_python_ok():
    """A supported branch at its latest patch asks for nothing."""
    lines, action = python_section("9.3.1", CYCLE, {"9.3": "9.3.1"})
    assert not action
    assert "- ✅ 9.3 is fully supported, until 2103-10." in lines
    assert "- ✅ 9.3.1 is the latest 9.3 patch." in lines


def test_python_patch():
    """A newer patch for the pinned branch asks for an update."""
    lines, action = python_section("9.3.0", CYCLE, {"9.3": "9.3.1"})
    assert action
    assert any(line.startswith("- ⬆️ 9.3.1 is out.") for line in lines)


def test_python_newer():
    """A newer supported branch is mentioned, without asking for anything."""
    lines, action = python_section("9.2.5", CYCLE, {"9.2": "9.2.5"})
    assert not action
    assert any("Python 9.3 is out, released 2098-10-01" in line for line in lines)
    # 9.4 is still in development, not a release to move to.
    assert not any("9.4" in line for line in lines)


def test_python_security():
    """A branch on security fixes only asks to plan the move."""
    lines, action = python_section("9.1.7", CYCLE, {"9.1": "9.1.7"})
    assert action
    assert any("only gets security fixes" in line for line in lines)


def test_python_eol():
    """A branch past its end of life asks to move now."""
    lines, action = python_section("9.0.3", CYCLE, {})
    assert action
    assert any("is no longer supported" in line for line in lines)


def test_python_offline():
    """Data that couldn't be fetched is said, and points to the page to check."""
    lines, _ = python_section("9.3.1", None, None)
    assert any("devguide.python.org/versions" in line for line in lines)
    assert any("latest patch releases" in line for line in lines)


def test_deps_current():
    """A lock that pip-compile --upgrade would leave alone asks for nothing."""
    lines, action = dependency_section({"somepkg": "1.0"}, {"somepkg": "1.0"})
    assert not action
    assert lines == ["✅ Every pin in `requirements.txt` is the newest allowed."]


def test_deps_outdated():
    """Each pin an upgrade would change is listed, new packages included."""
    current = {"oldpkg": "1.0", "steadypkg": "2.0"}
    upgraded = {"oldpkg": "3.0", "steadypkg": "2.0", "newpkg": "0.1"}
    lines, action = dependency_section(current, upgraded)
    assert action
    assert "- `oldpkg` 1.0 → 3.0" in lines
    assert "- `newpkg` not pinned → 0.1" in lines
    assert not any("steadypkg" in line for line in lines)


def test_body():
    """The issue mentions the owner and says up front whether to act."""
    quiet = issue_body("someone", ["py"], ["deps"], action=False)
    busy = issue_body("someone", ["py"], ["deps"], action=True)
    assert quiet.startswith("@someone, the monthly maintenance check. Nothing to do")
    assert "Something needs a look" in busy
