import csv
from pathlib import Path
from pages.books_toscrape.books_page import BooksPage


def test_scrape_books_to_csv(page):
    books_page = BooksPage(page)
    books_page.goto()

    books = books_page.get_all_books_data()
    assert len(books) > 0, "Expected to scrape at least one book"

    output_path = Path("scraped_books.csv")
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["title", "price"])
        writer.writeheader()
        writer.writerows(books)

    assert output_path.exists()
    with output_path.open(encoding="utf-8") as f:
        row_count = sum(1 for _ in f) - 1
    assert row_count == len(books)