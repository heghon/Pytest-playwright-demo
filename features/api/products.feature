Feature: Product catalog API
  As a consumer of the catalog service
  I want the product endpoints to answer predictably
  So that anything built on them can trust what comes back

  @api @JIRA-105
  Scenario: A known product comes back complete
    When I request product "1"
    Then the response status should be 200
    And the response should be JSON
    And the response should match the "product" schema

  @api @JIRA-106
  Scenario Outline: The catalog has no product "<product_id>"
    When I request product "<product_id>"
    Then the response status should be 404
    And the response should match the "error" schema
    And the error message should mention "<product_id>"

    Examples:
      | product_id |
      | 0          |
      | 999999     |
      | abc        |

  @api @JIRA-107
  Scenario: A page of products is the size it was asked for
    When I request 5 products starting from 10
    Then the response status should be 200
    And the response should match the "product_page" schema
    And the page should hold exactly 5 products
    And the page should report a skip of 10
    And every product on the page should match the "product" schema

  @api @JIRA-108
  Scenario: Searching narrows the catalog
    When I search the catalog for "mascara"
    Then the response status should be 200
    And the response should match the "product_page" schema
    And every product on the page should match the "product" schema
    And every product on the page should mention "mascara"
