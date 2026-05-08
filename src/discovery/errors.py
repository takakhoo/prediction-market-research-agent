class DiscoveryError(Exception):
    """Base error type for discovery runtime failures."""


class TDLibUnavailableError(DiscoveryError):
    """Base TDLib availability problem."""


class TDLibAuthRequiredError(TDLibUnavailableError):
    """Raised when an authorized TDLib session is not available."""


class TDLibRequestError(TDLibUnavailableError):
    """Raised when TDLib calls fail after retry policy."""


class WatchlistError(DiscoveryError):
    """Raised when watchlist operations cannot be completed."""
