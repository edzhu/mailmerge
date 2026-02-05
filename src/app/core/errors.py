"""Error taxonomy for the mail-merge emailer."""


class MailMergeError(Exception):
    """Base class for mail-merge related errors."""


class OptionalDependencyError(MailMergeError):
    """Raised when an optional dependency is missing."""


class ConfigurationError(MailMergeError):
    """Raised when configuration is invalid or incomplete."""


class TemplateValidationError(MailMergeError):
    """Raised when a template fails validation or parsing."""


class ExcelValidationError(MailMergeError):
    """Raised when spreadsheet content fails validation checks."""


class GraphClientError(MailMergeError):
    """Raised when the Microsoft Graph client encounters an error."""


class MergeError(MailMergeError):
    """Raised when the merge process fails."""


class RenderError(MailMergeError):
    """Raised when rendering a message body fails."""
