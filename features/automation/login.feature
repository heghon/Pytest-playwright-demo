Feature: Login validation
  As the SauceDemo team
  I want a bad sign-in attempt refused with a clear reason
  So that a user knows what went wrong and a locked account stays shut

  @automation @JIRA-104
  Scenario Outline: Login is refused for <username> with <password>
    Given I am on the SauceDemo login page
    When I log in as <username> with <password>
    Then login should be refused with "<message>"

    Examples:
      | username        | password           | message                                                                   |
      | locked_out_user | the valid password | Epic sadface: Sorry, this user has been locked out.                       |
      | not_a_user      | the valid password | Epic sadface: Username and password do not match any user in this service |
      | standard_user   | a wrong password   | Epic sadface: Username and password do not match any user in this service |
      | no username     | the valid password | Epic sadface: Username is required                                        |
      | standard_user   | no password        | Epic sadface: Password is required                                        |
