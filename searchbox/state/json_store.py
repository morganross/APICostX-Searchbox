"""Locked JSON file storage helpers."""

from __future__ import annotations

import fcntl
import json
import os
from collections.abc import Callable
from typing import Any


def file_paths(path_value: str) -> tuple[str, str]:
    data_file = path_value
    data_dir = os.path.dirname(data_file) or "."
    os.makedirs(data_dir, exist_ok=True)
    return data_file, data_file + ".lock"


def read_json_file_locked(path_value: str) -> dict[str, Any]:
    data_file, lock_file = file_paths(path_value)
    with open(lock_file, "a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_SH)
        try:
            try:
                with open(data_file, encoding="utf-8") as handle:
                    data = json.load(handle)
            except Exception:
                data = {}
            return data if isinstance(data, dict) else {}
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def write_json_file_locked(path_value: str, mutator: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
    data_file, lock_file = file_paths(path_value)
    with open(lock_file, "a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            try:
                with open(data_file, encoding="utf-8") as handle:
                    data = json.load(handle)
            except Exception:
                data = {}
            if not isinstance(data, dict):
                data = {}
            result = mutator(data)
            if isinstance(result, dict) and result is not data:
                data = result
            tmp_file = data_file + ".tmp"
            with open(tmp_file, "w", encoding="utf-8") as handle:
                json.dump(data, handle, sort_keys=True)
            os.replace(tmp_file, data_file)
            return result if isinstance(result, dict) else {}
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
