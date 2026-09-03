import csv
from pathlib import Path
import pytest
from pytest_bdd import scenarios, given, when, then, parsers
from pages.books_toscrape.books_page import BooksPage

scenarios("scraping/books_scraping.feature")


@pytest.fixture
def books_page(page):
    return BooksPage(page)


@given("I am on the book catalog page")
def go_to_books_page(books_page):
    books_page.goto()


# target_fixture: this step's return value becomes a fixture other steps can request by name.
@when("I scrape all the books on the page", target_fixture="scraped_books")
def scrape_books(books_page):
    return books_page.get_all_books()


@when(parsers.parse('I save the scraped books to "{filename}"'))
def save_books_to_csv(scraped_books, filename):
    with Path(filename).open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["title", "price"])
        writer.writeheader()
        writer.writerows(scraped_books)


@then(parsers.parse('"{filename}" should exist and contain one row per scraped book'))
def check_csv_well_formed(filename, scraped_books):
    output_path = Path(filename)
    assert output_path.exists(), f"{filename} was not created"
    with output_path.open(encoding="utf-8") as f:
        row_count = sum(1 for _ in f) - 1
    assert row_count == len(scraped_books)