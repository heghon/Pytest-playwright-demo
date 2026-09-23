Feature: Authentication API
  As the team behind the service
  I want a token to be required and to actually mean something
  So that a protected endpoint cannot be reached without one

  @api @JIRA-109
  Scenario: A valid login returns a token that works
    When I log in to the API with valid credentials
    Then the response status should be 200
    And the response should carry an access token
    When I request my own profile with that token
    Then the response status should be 200
    And the response should match the "user" schema
    And the profile should belong to the account I logged in as

  @api @JIRA-110
  Scenario Outline: The API refuses a login as "<username>" with "<password>"
    When I log in to the API as "<username>" with "<password>"
    Then the response status should be 400
    And the response should match the "error" schema
    And the error message should mention "<message>"

    # The API tells the two failure modes apart, and so should the test: a
    # missing field is not the same defect as a credential that does not match,
    # and a suite that accepted either message would not notice them swapping.
    Examples:
      | username    | password   | message                        |
      | emilys      | wrong_pass | Invalid credentials            |
      | no_one      | emilyspass | Invalid credentials            |
      | no username | emilyspass | Username and password required |

  @api @JIRA-111
  Scenario: The profile endpoint turns away an anonymous caller
    When I request my own profile with no token
    Then the response status should be 401
    And the response should match the "error" schema
    And the error message should mention "Access Token is required"

  # Asserts the correct behaviour, not the observed one. A malformed token is a
  # client error and belongs in a 401; the API under test answers 500. Writing
  # the test around the bug would hide it and would go red the day it is fixed,
  # so this scenario stays red until then — and the step attaches a note to the
  # report saying why, only while the status is wrong. Fix the API and both the
  # failure and its note disappear on their own.
  @api @JIRA-112
  Scenario: A malformed token is refused with a 401
    When I request my own profile with the token "garbage.token.here"
    Then the response status should be 401
    And the response should match the "error" schema
    And the error message should mention "invalid token"
