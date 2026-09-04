"""Opt-in production queue runtime; importing this package never opens a socket."""

from .production import ProductionWorker, RestrictedTransport, RuntimeFailure

__all__ = ["ProductionWorker", "RestrictedTransport", "RuntimeFailure"]
