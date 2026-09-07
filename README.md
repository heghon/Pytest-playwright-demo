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

Scenarios are written in [Gherkin](https://cucumber.io/docs/gherkin/) (`features/`) and wired to Playwright via [pytest-bdd](https://pytest-bdd.readthedocs.io/) step definitions (`stepdefs/`) — the folder structure mirrors category by category.

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

4. Set up environment variables:
   ```bash
   cp .env.example .env
   ```
   Then fill in real values in `.env` (for this demo, SauceDemo's public test
   credentials `standard_user` / `secret_sauce` work fine).

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
```

Run one file directly:
```bash
pytest stepdefs/ui_testing/test_todo_e2e.py
```

Add `--headed` to any command above to watch the browser instead of running headless.

## Test report

Every run writes a self-contained `reports/report.html`, and a failing scenario carries its own evidence inline: a screenshot, the video of the run, and a copyable `playwright show-trace` command.

CI publishes the latest run to **[the live report](https://heghon.github.io/Pytest-playwright-demo/)**, where each failure also gets a one-click link into the [Playwright trace viewer](https://trace.playwright.dev/) — no download, no terminal. The same bundle is attached to every run as the `playwright-report` artifact if you'd rather read it offline.

## Updating dependencies

```bash
pip install --upgrade $(pip freeze | awk -F'==' '{print $1}')
pip freeze > requirements.txt
playwright install
```

This upgrades every installed package to its latest compatible version, then re-pins `requirements.txt` to match.
Be aware, newer version of any dependency could introduce a breaking change.
Note : A dependabot is included with an automated weekly check & PR for actions & pip (installed packages), so the command is here just in case.

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

5. Reinstall from the project's actual direct dependencies —
   **note:** `pip install -r requirements.txt --upgrade` is a
   full `pip freeze` snapshot pinning every transitive dependency to
   versions resolved for the *old* Python, which can produce unsolvable
   conflicts against a new interpreter, so use the following:
```bash
   pip install pytest-playwright python-dotenv pytest-html pytest-bdd
   playwright install
   pip freeze > requirements.txt
```

6. Run the full suite or just one test before committing anything 
   to see if it works correctly:
```bash
   pytest
```

7. Update CI to match, in `.github/workflows/tests.yml`:
```yaml
   - name: Set up Python
     uses: actions/setup-python@v7
     with:
       python-version: "[NEW-VERSION]"
```

8. Check `.github/dependabot.yml` for any `ignore` rules that only
   existed to work around the *old* Python version's incompatibility
   with a package — they may no longer be needed.