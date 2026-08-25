import re
from playwright.sync_api import expect
from pages.base_page import BasePage


class TodoPage(BasePage):
    URL = "https://demo.playwright.dev/todomvc/"

    def goto(self):
        self.page.goto(self.URL)

    def add_todo(self, text: str):
        new_todo = self.page.get_by_placeholder("What needs to be done?")
        new_todo.fill(text)
        new_todo.press("Enter")

    def todo_items(self):
        return self.page.get_by_test_id("todo-item")

    def complete_todo(self, index: int):
        self.todo_items().nth(index).get_by_role("checkbox").check()

    def expect_todo_count(self, count: int):
        expect(self.todo_items()).to_have_count(count)

    def expect_todo_texts(self, texts: list[str]):
        expect(self.todo_items()).to_have_text(texts)

    def expect_todo_completed(self, index: int):
        expect(self.todo_items().nth(index)).to_have_class(re.compile("completed"))