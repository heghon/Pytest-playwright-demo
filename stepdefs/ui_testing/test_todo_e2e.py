import pytest
from pytest_bdd import scenarios, given, when, then, parsers
from pages.todomvc.todo_page import TodoPage

scenarios("ui_testing/todo.feature")


@pytest.fixture
def todo_page(page):
    return TodoPage(page)


@given("I am on the TodoMVC page")
def go_to_todo_page(todo_page):
    todo_page.goto()


@when("I add the following todo(s):")
def add_todos(todo_page, datatable):
    for row in datatable:
        todo_page.add_todo(row[0])


@then("I should see the following todo(s):")
def check_todos(todo_page, datatable):
    expected_texts = [row[0] for row in datatable]
    todo_page.expect_todo_count(len(expected_texts))
    todo_page.expect_todo_texts(expected_texts)


@when(parsers.parse('I mark the following todo(s) as completed:'))
def mark_todo_completed(todo_page, datatable):
    for row in datatable:
        todo_page.complete_todo_by_text(row[0])


@then(parsers.parse('The following todo(s) should be marked as completed:'))
def check_todo_completed(todo_page, datatable):
    for row in datatable:
            todo_page.expect_todo_completed_by_text(row[0])