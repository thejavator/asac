"""Static validation of a manifest (layer 1) against its variables (layer 2)."""

from asac.validate.checks import Issue, Severity, validate

__all__ = ["Issue", "Severity", "validate"]
