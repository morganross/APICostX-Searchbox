#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import subprocess
import sys


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def changed_files() -> list[str]:
    base_branch = os.environ.get("GITHUB_BASE_REF") or "open-source-productization"
    base = f"origin/{base_branch}"
    try:
        out = git("diff", "--name-only", "--diff-filter=ACMRTUXB", f"{base}...HEAD")
    except subprocess.CalledProcessError:
        out = git("diff", "--name-only", "--diff-filter=ACMRTUXB", "HEAD~1..HEAD")
    return [line.strip() for line in out.splitlines() if line.strip()]


files = changed_files()
failures: list[str] = []

for file in files:
    if file.startswith(("logs/", "data/", "playwright-report/", "test-results/")):
        failures.append(f"{file}: runtime/test output must not enter PR history")
    if file.startswith(("venv/", ".venv/", ".pytest_cache/", ".hypothesis/", ".ruff_cache/", "__pycache__/")):
        failures.append(f"{file}: local cache/dependency output must not be committed")
    if re.search(r"(^|/)\.env(\.|$)", file) and file != ".env.example":
        failures.append(f"{file}: env files must not be committed")
    if re.search(r"(^|/).*(\.bak|\.backup)(\.|$|[-_])", file):
        failures.append(f"{file}: backup files must not be committed")
    if file.endswith((".pem", ".key")):
        failures.append(f"{file}: private key material must not be committed")

if failures:
    print("ACM Searchbox GitHub gatekeeper failed:\n", file=sys.stderr)
    for failure in failures:
        print(f"- {failure}", file=sys.stderr)
    sys.exit(1)

print(f"ACM Searchbox GitHub gatekeeper passed ({len(files)} changed files checked).")
