Feature: Todo list management
  As a user of the TodoMVC app
  I want to add and complete todos
  So that I can track my tasks

  @ui @JIRA-101
  Scenario: Add two todos and complete one
    Given I am on the TodoMVC page
    When I add the following todo(s):
      | Buy groceries    |
      | Learn Playwright |
    Then I should see the following todo(s):
      | Buy groceries    |
      | Learn Playwright |
    When I mark the following todo(s) as completed:
      | Buy groceries    |
    Then The following todo(s) should be marked as completed:
      | Buy groceries    |