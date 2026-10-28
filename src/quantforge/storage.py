"""Compatibility imports for workspace persistence."""

from .runtime.workspace import load, lock, save

__all__ = ["load", "lock", "save"]
