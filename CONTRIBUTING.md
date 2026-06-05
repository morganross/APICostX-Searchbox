# Contributing

Thanks for helping improve Searchbox.

## Development Setup

```bash
python3 -m venv venv
. venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
```

## Checks

```bash
ruff check .
pytest
python -m py_compile main.py check_keys.py
```

Paid-provider live tests must be opt-in and should never run in default CI.

## Provider Contributions

New providers should include:

- documented environment variables
- quota settings
- parser tests with fixture responses
- missing-key behavior
- failure/cooldown behavior
- no secret leakage in logs/config

See `public-docs/providers/adding-a-provider.md`.
