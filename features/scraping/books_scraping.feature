Feature: Book catalog scraping
  As a data analyst
  I want to scrape book listings into a CSV file
  So that I can analyze pricing data offline

  @scraping @JIRA-102
  Scenario: Scrape book listings to CSV
    Given I am on the book catalog page
    When I scrape all the books on the page
    And I save the scraped books to "scraped_books.csv"
    Then "scraped_books.csv" should exist and contain one row per scraped book