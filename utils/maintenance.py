"""
The text of the monthly maintenance issue, opened by
.github/workflows/maintenance.yml on the 1st of every month.

It does the looking up, so the issue says what needs doing rather than only
asking you to go and check:

- Python: is the version in .python-version still supported, is a newer patch
  out for it, has a newer version been released. Support status comes from
  peps.python.org/api/release-cycle.json, the data behind
  devguide.python.org/versions; the latest patches from the manifest
  actions/setup-python installs from, so a version listed there is one CI can
  actually use.
- Dependencies: what pip-compile --upgrade would change in requirements.txt.

Run by hand to see this month's text, network permitting:

    python -m utils.maintenance requirements-upgraded.txt
"""

import json
import sys
import urllib.request
from pathlib import Path

from utils.venv_check import read_pins

ROOT = Path(__file__).resolve().parent.parent
RELEASE_CYCLE_URL = "https://peps.python.org/api/release-cycle.json"
MANIFEST_URL = (
    "https://raw.githubusercontent.com/actions/python-versions/main/"
    "versions-manifest.json"
)
VERSIONS_PAGE = "https://devguide.python.org/versions/"


def _version(text: str) -> tuple[int, ...]:
    """A version as numbers, so 3.14.10 sorts after 3.14.9."""
    return tuple(int(part) for part in text.split("."))


def latest_patches(manifest: list[dict]) -> dict[str, str]:
    """The newest stable release of each branch, e.g. {"3.14": "3.14.9"}."""
    latest = {}
    for release in manifest:
        if not release.get("stable"):
            continue
        version = release["version"]
        branch = ".".join(version.split(".")[:2])
        if branch not in latest or _version(version) > _version(latest[branch]):
            latest[branch] = version
    return latest


def python_section(
    pinned: str, cycle: dict | None, patches: dict | None
) -> tuple[list[str], bool]:
    """The Python part of the issue, and whether it asks for an action."""
    branch = ".".join(pinned.split(".")[:2])
    lines = [f"`.python-version` pins **{pinned}**."]
    action = False

    if cycle is None or branch not in cycle:
        lines.append(
            f"- ⚠️ Couldn't read the support status: check {VERSIONS_PAGE} by hand."
        )
    else:
        info = cycle[branch]
        status, eol = info["status"], info["end_of_life"]
        if status == "bugfix":
            lines.append(f"- ✅ {branch} is fully supported, until {eol}.")
        elif status == "security":
            action = True
            lines.append(
                f"- ⚠️ {branch} only gets security fixes now, and reaches its end "
                f"of life in {eol}: plan the move to a newer version."
            )
        else:
            action = True
            lines.append(
                f"- ❌ {branch} is no longer supported ({status}): move to a "
                "newer version."
            )
        newer = sorted(
            (name for name, info in cycle.items() if info["status"] == "bugfix"),
            key=_version,
        )
        newer = [name for name in newer if _version(name) > _version(branch)]
        for name in newer:
            lines.append(
                f"- ℹ️ Python {name} is out, released "
                f"{cycle[name]['first_release']}. Optional while {branch} is "
                "supported: check every dependency supports it first."
            )

    if patches is None:
        lines.append("- ⚠️ Couldn't read the latest patch releases.")
    elif branch in patches:
        latest = patches[branch]
        if _version(latest) > _version(pinned):
            action = True
            lines.append(
                f"- ⬆️ {latest} is out. Patch releases only fix bugs and "
                "security issues, so this one is worth taking."
            )
        else:
            lines.append(f"- ✅ {pinned} is the latest {branch} patch.")

    if action:
        lines.append(
            "\nThe steps are in the README, under *Updating Python*. Nothing "
            "changes on its own."
        )
    return lines, action


def dependency_section(current: dict, upgraded: dict) -> tuple[list[str], bool]:
    """The dependency part of the issue, and whether it asks for an action."""
    changes = [
        f"- `{name}` {current.get(name, 'not pinned')} → {version}"
        for name, version in sorted(upgraded.items())
        if current.get(name) != version
    ]
    if not changes:
        return ["✅ Every pin in `requirements.txt` is the newest allowed."], False
    return [
        f"`pip-compile --upgrade` would change {len(changes)} pin(s):",
        *changes,
        "",
        (
            "Dependabot should be proposing these already. If no open pull "
            "request covers them, refresh the lock by hand, as the README's "
            "*Updating dependencies* explains:"
        ),
        "```bash",
        "pip-compile --strip-extras --upgrade requirements.in",
        "pip-sync requirements.txt",
        "playwright install",
        "python check.py",
        "```",
    ], True


def issue_body(owner: str, python: list[str], deps: list[str], action: bool) -> str:
    """The whole issue, mentioning the owner so it reaches their notifications."""
    verdict = (
        "Something needs a look, see below."
        if action
        else "Nothing to do this month: close this issue."
    )
    return "\n".join(
        [
            f"@{owner}, the monthly maintenance check. {verdict}",
            "",
            "## Python",
            *python,
            "",
            "## Dependencies",
            *deps,
            "",
            (
                "Close this issue once it's handled. Next month's check opens a "
                "new one and closes this one if it's still open."
            ),
        ]
    )


def _fetch(url: str):
    """The JSON at url, or None if it can't be fetched: the issue says so instead."""
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            return json.load(response)
    except (OSError, ValueError):
        return None


def main(upgraded_lock: str, owner: str = "") -> int:
    pinned = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
    manifest = _fetch(MANIFEST_URL)
    python, python_action = python_section(
        pinned,
        _fetch(RELEASE_CYCLE_URL),
        latest_patches(manifest) if manifest is not None else None,
    )
    deps, deps_action = dependency_section(
        read_pins((ROOT / "requirements.txt").read_text(encoding="utf-8")),
        read_pins(Path(upgraded_lock).read_text(encoding="utf-8")),
    )
    owner = owner or "owner"
    print(issue_body(owner, python, deps, python_action or deps_action))
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
