import csv
from pathlib import Path
from playwright.sync_api import Page


def test_scrape_books_to_csv(page: Page):
    # 1. Go to the scraping practice site
    page.goto("https://books.toscrape.com/")

    # 2. Every book on the page lives inside an <article class="product_pod"> element
    book_cards = page.locator("article.product_pod")

    # 3. Loop through each book card and pull out the title + price
    books = []
    for card in book_cards.all():
        title = card.locator("h3 a").get_attribute("title")
        price_text = card.locator("p.price_color").inner_text()
        price = float(price_text.replace("£", ""))
        books.append({"title": title, "price": price})

    # 4. Sanity check before we bother writing a file
    assert len(books) > 0, "Expected to scrape at least one book"

    # 5. Write results to a CSV file
    output_path = Path("scraped_books.csv")
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["title", "price"])
        writer.writeheader()
        writer.writerows(books)

    # 6. Confirm the file was created with the right number of rows
    assert output_path.exists()
    with output_path.open(encoding="utf-8") as f:
        row_count = sum(1 for _ in f) - 1  # minus 1 for the header row
    assert row_count == len(books)