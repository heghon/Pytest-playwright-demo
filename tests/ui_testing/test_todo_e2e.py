import pytest
from pages.todomvc.todo_page import TodoPage


@pytest.mark.ui
def test_add_and_complete_todo(page):
    todo_page = TodoPage(page)
    
    todo_page.goto()

    todo_page.add_todo("Buy groceries")
    todo_page.add_todo("Learn Playwright")

    todo_page.expect_todo_count(2)
    todo_page.expect_todo_texts(["Buy groceries", "Learn Playwright"])

    todo_page.complete_todo(0)
    todo_page.expect_todo_completed(0)