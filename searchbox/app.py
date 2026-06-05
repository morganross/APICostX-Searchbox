"""FastAPI application entrypoint.

This module is a transitional bridge while the application is being moved out of
the legacy top-level ``main.py`` module. New integrations may import
``searchbox.app:app``; existing ``main:app`` deployments continue to work.
"""

from main import app

__all__ = ["app"]
