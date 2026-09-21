"""Stooge domain exceptions."""


class StoogeError(Exception):
    """Base exception for Stooge."""

    kind = "error"

    def __init__(self, message: str, **payload):
        super().__init__(message)
        self.payload = payload


class StoogeInitError(StoogeError, RuntimeError):
    """Raised when something is wrong with the project setup."""

    kind = "init_error"


class StoogeParseError(StoogeError, ValueError):
    """Raised when a Stooge project cannot be parsed or validated."""

    kind = "parse_error"


class StoogeTaskNotFoundError(StoogeError, ValueError):
    """Raised when a requested task ID is not present in the project."""

    kind = "task_not_found"


class StoogeRunError(StoogeError, RuntimeError):
    """Raised when a task cannot be executed successfully."""

    kind = "run_error"
