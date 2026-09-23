![Tests](https://github.com/heghon/Pytest-playwright-demo/actions/workflows/tests.yml/badge.svg)

# Pytest-Playwright Demo

A demo project showcasing three classic browser automation patterns using
[Playwright](https://playwright.dev/python/) and [pytest](https://docs.pytest.org/),
run against public practice websites.

## What's included

| Feature file | Step definitions | Pattern | Target site |
|---|---|---|---|
| `features/ui_testing/todo.feature` | `stepdefs/ui_testing/test_todo_e2e.py` | End-to-end UI testing | [demo.playwright.dev/todomvc](https://demo.playwright.dev/todomvc/) |
| `features/scraping/books_scraping.feature` | `stepdefs/scraping/test_books_scraper.py` | Web scraping (outputs `scraped_books.csv`) | [books.toscrape.com](https://books.toscrape.com) |
| `features/automation/checkout.feature` | `stepdefs/automation/test_checkout_flow.py` | Login + user flow automation | [saucedemo.com](https://www.saucedemo.com) |
| `features/automation/login.feature` | `stepdefs/automation/test_login.py` | Negative paths, data-driven with a `Scenario Outline` | [saucedemo.com](https://www.saucedemo.com) |
| `features/api/products.feature` | `stepdefs/api/test_products.py` | API testing — status codes, JSON Schema, pagination | [dummyjson.com](https://dummyjson.com) |
| `features/api/auth.feature` | `stepdefs/api/test_auth.py` | API testing — tokens and rejected authentication | [dummyjson.com](https://dummyjson.com) |

Scenarios are written in [Gherkin](https://cucumber.io/docs/gherkin/) (`features/`) and wired to Playwright via [pytest-bdd](https://pytest-bdd.readthedocs.io/) step definitions (`stepdefs/`) — the folder structure mirrors category by category.

Browser scenarios drive page objects in `pages/`; the API scenarios drive clients in `api/` and check responses against the [JSON Schema](https://json-schema.org/) documents in `api/schemas/`. The API tests use Playwright's own HTTP client, so they need no extra dependency and start no browser.

## Setup

1. Clone the repo and enter the folder:
   ```bash
   git clone https://github.com/heghon/Pytest-playwright-demo
   cd Pytest-playwright-demo
   ```

2. Create and activate a virtual environment:
   - For Windows :
   ```bash
   python3 -m venv venv
   source venv\Scripts\activate
   ```
   - For the rest of the world :
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   playwright install
   ```
   That covers Chromium, Firefox and WebKit. Google Chrome and Microsoft Edge
   are the real branded browsers rather than Playwright's own builds, so they
   are installed separately and only if you want to run against them:
   ```bash
   playwright install chrome
   playwright install msedge
   ```

4. Set up environment variables:
   ```bash
   cp .env.example .env
   ```
   Then fill in real values in `.env` (for this demo, SauceDemo's public test
   credentials `standard_user` / `secret_sauce` work fine).

5. To make CI work on a fork, mirror that same `.env` into GitHub as a **single**
   secret: Settings → Secrets and variables → Actions → New repository secret,
   named `DOTENV`, whose value is the whole file rather than one secret per line.
   The workflow writes it back out to `.env` before running the suite, so adding a
   variable later means editing the secret and never the workflow. While you're in
   Settings, set Pages → Source to **GitHub Actions** so the report can publish.

## Running the tests

Run everything:
```bash
pytest
```

Run one category, by Gherkin tag:
```bash
pytest -m ui           # just the UI scenario(s)
pytest -m scraping     # just the scraping scenario(s)
pytest -m automation   # just the automation scenario(s)
pytest -m api          # just the API scenario(s), no browser started
```

Run everything tagged with one issue:
```bash
pytest --jira JIRA-105
pytest --jira 105        # the JIRA- prefix is optional
```

`-m` cannot do this: the `@JIRA-xxx` tags are folded into a single `jira_key`
marker that carries the key as an argument, and `-m` only matches marker names.
A key nothing is tagged with reports the keys that exist rather than running nothing.

Run one file directly:
```bash
pytest stepdefs/ui_testing/test_todo_e2e.py
```

Add `--headed` to any command above to watch the browser instead of running headless.

### Choosing a browser

Runs use Chromium unless you say otherwise:

```bash
pytest --browser firefox
pytest --browser webkit                              # the engine behind Safari
pytest --browser chromium --browser-channel chrome   # real Google Chrome
pytest --browser chromium --browser-channel msedge   # real Microsoft Edge
```

`--browser` can be repeated to run every scenario on several engines in one go,
which puts them all in the same report, one row each:

```bash
pytest --browser chromium --browser firefox --browser webkit
```

The engine each scenario ran on shows up in the report's **Engine** column.

On CI the suite only runs when you start it yourself — Actions → Playwright Tests
→ Run workflow — where the same engines are a dropdown, alongside one for the tag
to run and a free-text box for a single JIRA issue. The issue wins over the tag if
both are given. Run the whole suite from `main` and the report is published to
Pages; a run narrowed to one tag or one issue stays as a downloadable artifact
instead, so a partial result never replaces the published one. 
The other triggers (on push, nightly, and a few
more) are written out and commented at the top of
[`.github/workflows/tests.yml`](.github/workflows/tests.yml), ready to switch on.

## Test report

Every run writes `reports/`, a self-contained folder: `index.html` plus the failure artifacts under `test-artifacts/`. Results are filed under the category folder and then the feature they came from, both foldable, so the table stays readable as the suite grows. A failing scenario carries its own evidence inline — a screenshot, the video of the run, and a copyable `playwright show-trace` command, which resolves from `reports/` itself. Delete the folder and the run leaves no trace behind.

CI publishes the latest run to **[the live report](https://heghon.github.io/Pytest-playwright-demo/)**, where each failure also gets a one-click link into the [Playwright trace viewer](https://trace.playwright.dev/) — no download, no terminal. The same bundle is attached to every run as the `playwright-report` artifact if you'd rather read it offline.

## Updating dependencies

Two files, and only one of them is written by hand:

| File | What it is |
|---|---|
| `requirements.in` | the packages this project actually imports — edit this one |
| `requirements.txt` | every pin, generated from the `.in` and annotated with `# via <parent>` |

To add or remove a package, edit `requirements.in`, then regenerate the lock:

```bash
pip install pip-tools
pip-compile --strip-extras requirements.in
playwright install
```

To pull in newer versions of everything, add `--upgrade`:

```bash
pip-compile --strip-extras --upgrade requirements.in
```

**Never rebuild `requirements.txt` with `pip freeze`.** A freeze lists direct and
transitive packages alike with no record of which is which, so Dependabot reads
every line as a deliberate choice and will happily bump a package like `pyee`
past the range `playwright` allows — producing a lock that cannot be installed
at all. The `# via` annotations are what keep that from happening.

Dependabot opens a weekly PR for pip and for the Actions. Its pull requests are
the one case CI reacts to automatically: the `dependencies` job resolves the lock
on the PR, so a bump that cannot be installed is caught before it reaches `main`.

## Updating Python

Check current support status and end-of-life dates at
[devguide.python.org/versions](https://devguide.python.org/versions/).
This project uses [pyenv](https://github.com/pyenv/pyenv) to manage
Python versions.

1. Install the new version via pyenv and pin it for this project:
```bash
   pyenv install [NEW-VERSION]
   echo "[NEW-VERSION]" > .python-version
```

2. **Open a brand-new terminal window before continuing.** pyenv only
   takes effect in shells started *after* it's been configured — reusing
   an existing terminal tab will silently keep using the old Python.

3. From the new terminal, confirm the switch actually worked *before*
   touching the venv:
```bash
   cd [path-to-your-repository]
   python3 --version
   which python3
```
   This should report the new version, with a path under
   `.pyenv/shims/` — not `/Library/Developer/CommandLineTools/`. 
   If it doesn't, run `echo $SHELL` and make sure pyenv's init line is in the
   config file your shell actually loads (`~/.zshrc` for zsh,
   `~/.bash_profile` for bash).

4. Rebuild the virtual environment from scratch — an existing `venv/` is
   tied to whichever Python built it and can't be upgraded in place:
```bash
   rm -rf venv
   python3 -m venv venv
   source venv/bin/activate
   python --version
```
   Confirm this also reports the new version, from *inside* the
   activated venv.

5. Re-resolve the dependencies against the new interpreter —
   **note:** `pip install -r requirements.txt` on its own reuses pins that were
   resolved for the *old* Python, and one of them may have no release that
   supports the new one. Recompiling from `requirements.in` works the whole
   graph out again, so use the following:
```bash
   pip install pip-tools
   pip-compile --strip-extras --upgrade requirements.in
   pip install -r requirements.txt
   playwright install
```
   The direct dependencies live in `requirements.in` and nowhere else, so there
   is no list here to fall out of step with it. Commit both files: the `.in` is
   unchanged, but `requirements.txt` now holds the versions the new Python
   resolved to.

6. Run the full suite or just one test before committing anything 
   to see if it works correctly:
```bash
   pytest
```

7. Nothing to do for CI. Both jobs in `.github/workflows/tests.yml` set
   `python-version-file: .python-version`, so the file you edited in step 1 is
   the only place the version is written — commit it and the runners follow.

8. Check `.github/dependabot.yml` for any `ignore` rules that only
   existed to work around the *old* Python version's incompatibility
   with a package — they may no longer be needed.