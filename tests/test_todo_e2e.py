import re
from playwright.sync_api import Page, expect


def test_add_and_complete_todo(page: Page):
    # 1. Navigate to the TodoMVC demo app
    page.goto("https://demo.playwright.dev/todomvc/")

    # 2. Locate the input field where new todos are typed
    new_todo = page.get_by_placeholder("What needs to be done?")

    # 3. Type a todo and press Enter to add it
    new_todo.fill("Buy groceries")
    new_todo.press("Enter")

    # 4. Add a second todo the same way
    new_todo.fill("Learn Playwright")
    new_todo.press("Enter")

    # 5. Assert both todos are now visible in the list
    todo_items = page.get_by_test_id("todo-item")
    expect(todo_items).to_have_count(2)
    expect(todo_items).to_have_text(["Buy groceries", "Learn Playwright"])

    # 6. Mark the first todo as completed by clicking its checkbox
    todo_items.nth(0).get_by_role("checkbox").check()

    # 7. Assert it now carries the "completed" CSS class
    expect(todo_items.nth(0)).to_have_class(re.compile("completed"))