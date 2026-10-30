"""
The published site on GitHub Pages, kept across runs. Used by the CI workflow.

A Pages deployment replaces the whole site, so anything a run should keep, the
report history above all, has to be fetched from the live site first and
published again with the new run. Each deployment therefore also publishes
site-manifest.json, the list of every file in it, which is what the next run
fetches by.

    python -m utils.site fetch BASE_URL DEST --history DIR
        Downloads the published site into DEST, and its history/ into DIR, where
        pytest compares against it and archives the new run. Nothing published
        yet is not an error: the history starts empty.

    python -m utils.site assemble --front DIR --history DIR --out DIR
        Builds the site to deploy: the front page from --front (this run's
        reports/ after a full run, the previously published site otherwise),
        plus the history. Exits with code 3 when --front has no report, so a
        filtered run never publishes a site without a front page.
"""

import argparse
import json
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

MANIFEST = "site-manifest.json"
HISTORY = "history"


def _download(url: str, timeout: int = 30) -> bytes | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.read()
    except (urllib.error.URLError, OSError, ValueError):
        return None


def fetch(base_url: str, dest: Path, history: Path) -> int:
    """Downloads the published site. Returns how many files came down."""
    base_url = base_url.rstrip("/")
    raw = _download(f"{base_url}/{MANIFEST}")
    files = []
    if raw is not None:
        try:
            files = json.loads(raw).get("files", [])
        except ValueError:
            files = []

    fetched = 0
    for name in files:
        # Only paths inside the site: a manifest is data, never a way out.
        target = (dest / name).resolve()
        if not target.is_relative_to(dest.resolve()):
            continue
        content = _download(f"{base_url}/{name}")
        if content is None:
            print(f"Could not fetch {name}, carrying on without it.")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        fetched += 1

    if history.exists():
        shutil.rmtree(history)
    if (dest / HISTORY).is_dir():
        shutil.copytree(dest / HISTORY, history)
    else:
        history.mkdir(parents=True)
    print(f"Fetched {fetched} of {len(files)} published files.")
    return fetched


def manifest(site: Path) -> list[str]:
    """Every file in the site, as paths from its root, the manifest itself aside."""
    return sorted(
        path.relative_to(site).as_posix()
        for path in site.rglob("*")
        if path.is_file() and path.name != MANIFEST
    )


def assemble(front: Path, history: Path, out: Path) -> bool:
    """Builds the site to deploy in `out`. False when there is no front page."""
    if not (front / "index.html").is_file():
        print(f"No report in {front}: nothing to put on the front page.")
        return False
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(front, out, ignore=shutil.ignore_patterns(HISTORY, MANIFEST))
    if history.is_dir():
        shutil.copytree(history, out / HISTORY)
    files = manifest(out)
    (out / MANIFEST).write_text(
        json.dumps({"files": files}, indent=1), encoding="utf-8"
    )
    size = sum((out / name).stat().st_size for name in files)
    print(f"Site assembled: {len(files)} files, {size / 1024 / 1024:.1f} MB.")
    return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m utils.site")
    commands = parser.add_subparsers(dest="command", required=True)
    get = commands.add_parser("fetch")
    get.add_argument("base_url")
    get.add_argument("dest", type=Path)
    get.add_argument("--history", type=Path, required=True)
    build = commands.add_parser("assemble")
    build.add_argument("--front", type=Path, required=True)
    build.add_argument("--history", type=Path, required=True)
    build.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.command == "fetch":
        fetch(args.base_url, args.dest, args.history)
        return 0
    return 0 if assemble(args.front, args.history, args.out) else 3


if __name__ == "__main__":
    sys.exit(main())
