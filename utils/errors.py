class NoDataScrapedError(Exception):
    """Raised when a scraper finds zero items where at least one was expected."""