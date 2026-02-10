"""
stooge exceptions.
"""


class SPFException(Exception):
    """Base exception for stooge."""


class SPFInitError(SPFException, RuntimeError):
    """Raised with something is wrong the project setup."""
