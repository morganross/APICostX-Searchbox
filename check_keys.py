from pathlib import Path
import os

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None


if load_dotenv:
    load_dotenv(Path(__file__).resolve().parent / ".env")

for name in (
    "SERPER_API_KEY",
    "BRAVE_API_KEY",
    "SCIENCESTACK_API_KEY",
    "SEARCHAPI_API_KEY",
    "SERPAPI_API_KEY",
    "AGENTIC_DATA_API_KEY",
    "OANOR_API_KEY",
):
    status = "configured" if os.environ.get(name) else "missing"
    print(f"{name}: {status}")
