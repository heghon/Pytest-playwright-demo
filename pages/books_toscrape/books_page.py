from pages.base_page import BasePage
from utils.errors import NoDataScrapedError

class BooksPage(BasePage):
    URL = "https://books.toscrape.com/"

    def goto(self):
        self.page.goto(self.URL)

    def get_all_books(self) -> list[dict]:
        book_cards = self.page.locator("article.product_pod")
        books = []
        for card in book_cards.all():
            title = card.locator("h3 a").get_attribute("title")
            price_text = card.locator("p.price_color").inner_text()
            price = float(price_text.replace("£", ""))
            books.append({"title": title, "price": price})

        if not books:
            raise NoDataScrapedError(
                "No books were found on the page — the site layout may have "
                "changed, or the page failed to load correctly."
            )
        return books