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

## Updating dependencies

```bash
pip install --upgrade $(pip freeze | awk -F'==' '{print $1}')
pip freeze > requirements.txt
playwright install
```

This upgrades every installed package to its latest compatible version, then re-pins `requirements.txt` to match.
Be aware, newer version of any dependency could introduce a breaking change.
Note : A dependabot is included with an automated weekly check & PR for actions & pip (installed packages), so the command is here just in case.