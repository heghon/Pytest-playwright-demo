Feature: Framework smoke check
  As the maintainer of this suite
  I want a few scenarios that walk through every part of the framework
  So that a dependency bump that breaks it is caught before it is merged

  # Run by CI on every Dependabot pull request, and left out of every other run
  # by the -m "not smoke" in pytest.ini. You can ask for it with: pytest -m smoke
  #
  # The products come from a stub server the test starts itself, never from the
  # network so a fail is never due to something else than the framework. What it
  # does go through is everything else the real scenarios rely on: a Background,
  # a data table, a Scenario Outline, target_fixture, the shared API steps,
  # report_note, JSON Schema, Playwright's HTTP client and the HTML report.

  Background:
    Given the stub serves these products:
      | id | title         | price |
      | 1  | Smoke Lantern | 9.99  |

  @smoke
  Scenario: The stub hands back the product it was given
    When I request product "1" from the stub
    Then the response status should be 200
    And the response should be JSON
    And the response should match the "product" schema
    And the product should be the one the stub was given

  @smoke
  Scenario Outline: The stub has no product "<product_id>"
    When I request product "<product_id>" from the stub
    Then the response status should be 404
    And the response should match the "error" schema
    And the error message should mention "<product_id>"

    Examples:
      | product_id |
      | 2          |
      | abc        |
