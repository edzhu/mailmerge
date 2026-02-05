"""Error taxonomy for the mail-merge emailer."""


class MailMergeError(Exception):
    """Base class for mail-merge related errors."""


class OptionalDependencyError(MailMergeError):
    """Raised when an optional dependency is missing."""


class ConfigurationError(MailMergeError):
    """Raised when configuration is invalid or incomplete."""
