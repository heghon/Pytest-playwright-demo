# Pytest-Playwright Demo

A demo project showcasing three classic browser automation patterns using
[Playwright](https://playwright.dev/python/) and [pytest](https://docs.pytest.org/),
run against public practice websites.

## What's included

| Test file | Pattern | Target site |
|---|---|---|
| `tests/test_todo_e2e.py` | End-to-end UI testing | [demo.playwright.dev/todomvc](https://demo.playwright.dev/todomvc/) |
| `tests/test_books_scraper.py` | Web scraping (outputs `scraped_books.csv`) | [books.toscrape.com](https://books.toscrape.com) |
| `tests/test_checkout_flow.py` | Login + user flow automation | [saucedemo.com](https://www.saucedemo.com) |

## Setup

1. Clone the repo and enter the folder:
   ```bash
   git clone <your-repo-url>
   cd Pytest-playwright-demo
   ```

2. Create and activate a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate   # on Windows: venv\Scripts\activate
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

Run a single file:
```bash
pytest tests/test_todo_e2e.py
```
Add --headed to any command to watch the browser while it runs, instead of
running headless.