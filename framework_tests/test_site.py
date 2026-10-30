"""
The published site's round trip in utils/site.py: assembled on one run, fetched
back on the next. file:// addresses stand in for the live site, so nothing here
touches the network.
"""

import json

from utils.site import MANIFEST, assemble, fetch, manifest


def _report(folder, text="report"):
    """A report folder as pytest leaves it."""
    (folder / "test-artifacts").mkdir(parents=True)
    (folder / "index.html").write_text(text)
    (folder / "test-artifacts" / "shot.png").write_bytes(b"png")
    return folder


def _history(folder):
    """A history with one archived run."""
    run = folder / "all-chromium" / "2099-01-01T10-00-00Z"
    run.mkdir(parents=True)
    (run / "index.html").write_text("old run")
    return folder


def test_assemble_full(tmp_path):
    """After a full run, the front page is its report, with the history beside it."""
    out = tmp_path / "public"
    assert assemble(_report(tmp_path / "reports"), _history(tmp_path / "h"), out)
    assert (out / "index.html").read_text() == "report"
    assert (out / "history" / "all-chromium" / "2099-01-01T10-00-00Z").is_dir()


def test_assemble_keeps_front(tmp_path):
    """After a filtered run, the front page is the one already published."""
    published = _report(tmp_path / "published", text="last full run")
    (published / "history").mkdir()
    (published / "history" / "stale.txt").write_text("old history")
    (published / MANIFEST).write_text("{}")
    out = tmp_path / "public"
    assert assemble(published, _history(tmp_path / "h"), out)
    assert (out / "index.html").read_text() == "last full run"
    # The history is the one pytest just extended, never the stale published one.
    assert not (out / "history" / "stale.txt").exists()


def test_assemble_no_front(tmp_path):
    """With no front page to publish, nothing is assembled."""
    (tmp_path / "published").mkdir()
    assert not assemble(tmp_path / "published", tmp_path / "h", tmp_path / "public")
    assert not (tmp_path / "public").exists()


def test_manifest(tmp_path):
    """The manifest lists every file of the site, itself aside."""
    out = tmp_path / "public"
    assemble(_report(tmp_path / "reports"), _history(tmp_path / "h"), out)
    files = json.loads((out / MANIFEST).read_text())["files"]
    assert files == manifest(out)
    assert "index.html" in files
    assert "history/all-chromium/2099-01-01T10-00-00Z/index.html" in files
    assert MANIFEST not in files


def test_fetch_round_trip(tmp_path):
    """What one run publishes, the next fetches back, history included."""
    site = tmp_path / "public"
    assemble(_report(tmp_path / "reports"), _history(tmp_path / "h"), site)
    history = tmp_path / "report-history"
    fetched = fetch(site.as_uri(), tmp_path / "published", history)
    assert fetched == len(manifest(site))
    assert (tmp_path / "published" / "index.html").read_text() == "report"
    assert (history / "all-chromium" / "2099-01-01T10-00-00Z" / "index.html").is_file()


def test_fetch_nothing(tmp_path):
    """Nothing published yet: no error, and an empty history to start from."""
    history = tmp_path / "report-history"
    assert fetch((tmp_path / "nowhere").as_uri(), tmp_path / "published", history) == 0
    assert history.is_dir() and not any(history.iterdir())


def test_fetch_stays_inside(tmp_path):
    """A manifest entry pointing outside the site is never written."""
    # The live site and the download in separate trees, so a file escaping the
    # download folder would land somewhere nothing else puts one.
    site = tmp_path / "server" / "public"
    site.mkdir(parents=True)
    (site / MANIFEST).write_text(json.dumps({"files": ["../escaped.txt"]}))
    (tmp_path / "server" / "escaped.txt").write_text("outside")
    dest = tmp_path / "runner" / "published"
    assert fetch(site.as_uri(), dest, tmp_path / "runner" / "h") == 0
    assert not (tmp_path / "runner" / "escaped.txt").exists()
