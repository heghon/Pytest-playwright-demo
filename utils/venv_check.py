"""
Whether the active environment is the one requirements.txt describes.

pip install -r adds and upgrades but never removes, and nothing reinstalls on its
own after a lock changes, so a venv can quietly fall behind. Two kinds of
drift are reported. A pinned package at another version, or missing. And a
pytest plugin the lock doesn't know about, because pytest loads every installed
plugin by itself, so a stray one changes how the suite runs. Any other extra
package is left alone: pip-tools and its dependencies have to be installed, and
an unused package changes nothing.
"""

import re
from importlib.metadata import distributions
from pathlib import Path

REQUIREMENTS = Path(__file__).resolve().parent.parent / "requirements.txt"

FIX = "pip-sync requirements.txt\n  playwright install"


def _normalised(name: str) -> str:
    """A package name as pip compares them: case and -_. separators don't count."""
    return re.sub(r"[-_.]+", "-", name).lower()


def read_pins(text: str) -> dict[str, str]:
    """The name==version pins of a requirements file, by normalised name."""
    pins = {}
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if "==" in line:
            name, version = line.split("==", 1)
            pins[_normalised(name)] = version.strip()
    return pins


def installed_packages() -> tuple[dict[str, str], set[str]]:
    """Every installed package with its version, and the names of pytest plugins."""
    versions, plugins = {}, set()
    for dist in distributions():
        name = _normalised(dist.metadata["Name"])
        versions[name] = dist.version
        if any(entry.group == "pytest11" for entry in dist.entry_points):
            plugins.add(name)
    return versions, plugins


def drift(
    pins: dict[str, str], installed: dict[str, str], plugins: set[str]
) -> list[str]:
    """One line per difference between the pins and what is installed."""
    problems = []
    for name, pinned in sorted(pins.items()):
        actual = installed.get(name)
        if actual is None:
            problems.append(f"{name}: not installed, {pinned} pinned")
        elif actual != pinned:
            problems.append(f"{name}: {actual} installed, {pinned} pinned")
    for name in sorted(plugins - pins.keys()):
        problems.append(f"{name}: a pytest plugin that requirements.txt doesn't pin")
    return problems


def check() -> list[str]:
    """The drift of the active environment from requirements.txt."""
    installed, plugins = installed_packages()
    return drift(
        read_pins(REQUIREMENTS.read_text(encoding="utf-8")), installed, plugins
    )


def message(problems: list[str]) -> str:
    """What to tell someone whose venv has drifted, and how to fix it."""
    listed = "\n".join(f"  {problem}" for problem in problems)
    return (
        "The venv doesn't match requirements.txt:\n"
        f"{listed}\n\n"
        f"Bring it in line, then run again:\n  {FIX}"
    )
