"""Shared runtime defaults used by request models and legacy entrypoints."""

import os

BRAVE_DEFAULT_COUNT = int(os.environ.get("BRAVE_DEFAULT_COUNT", "10"))
BRAVE_MAX_COUNT = int(os.environ.get("BRAVE_MAX_COUNT", "20"))
SERPER_DEFAULT_COUNT = int(os.environ.get("SERPER_DEFAULT_COUNT", str(BRAVE_DEFAULT_COUNT)))
SERPER_MAX_COUNT = int(os.environ.get("SERPER_MAX_COUNT", "20"))
