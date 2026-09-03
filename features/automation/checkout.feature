Feature: Checkout flow
  As a shopper
  I want to add an item to my cart and complete checkout
  So that I can finish a purchase

  @automation @JIRA-103
  Scenario: Add an item to the cart and complete checkout
    Given I am logged in to SauceDemo
    When I add the following items to the cart:
      | Sauce Labs Backpack   |
      | Sauce Labs Bike Light |
    Then the cart badge should show 2
    When I go to the cart
    And I proceed to checkout
    And I fill in my checkout information:
      | first_name | last_name | zip_code |
      | Ada        | Lovelace  | 75000    |
    Then the overview should list:
      | Sauce Labs Backpack   |
      | Sauce Labs Bike Light |
    Then I can finish my order and see the confirmation