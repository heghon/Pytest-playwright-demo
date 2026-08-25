from pages.base_page import BasePage


class BooksPage(BasePage):
    URL = "https://books.toscrape.com/"

    def goto(self):
        self.page.goto(self.URL)

    def get_all_books_data(self) -> list[dict]:
        book_cards = self.page.locator("article.product_pod")
        books = []
        for card in book_cards.all():
            title = card.locator("h3 a").get_attribute("title")
            price_text = card.locator("p.price_color").inner_text()
            price = float(price_text.replace("£", ""))
            books.append({"title": title, "price": price})
        return books