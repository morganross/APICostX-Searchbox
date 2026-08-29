# CodexExecAPI GPT-5.6 Reasoning Report

## Objective

Expose GPT-5.6 Sol, Terra, and Luna through APICostX while keeping the public
reasoning contract limited to Low, Medium, and High.

## Implemented contract

| APICostX value | Codex CLI value |
| --- | --- |
| `low` | `low` |
| `medium` | `medium` |
| `high` | `xhigh` |

APICostX persists only the three public values. CodexExecAPI performs the High
to Extra High translation immediately before constructing `codex exec` args.
Unknown public values fail with HTTP 400.

## Changes

- Added `codexexecapi:gpt-5.6-sol`, `codexexecapi:gpt-5.6-terra`, and
  `codexexecapi:gpt-5.6-luna` to the APICostX model registry.
- Added a Low/Medium/High FPF reasoning selector and preset round trip.
- Added all three GPT-5.6 models to FilePromptForge's CodexExecAPI allowlist.
- Corrected FilePromptForge to send top-level `reasoning_effort`.
- Changed missing FPF reasoning to Medium instead of High.
- Added strict CodexExecAPI reasoning validation and advertised mapping metadata.
- Upgraded the production Codex CLI from `0.142.0` to `0.151.0`.

## Failure and exact cause

The first direct Luna request failed with HTTP 502. Its CLI event log contained
an OpenAI HTTP 400 response stating that GPT-5.6 Luna required a newer Codex
version. The runner was using an old standalone `0.142.0` binary even though a
separate npm installation existed. Production now explicitly uses
`/usr/local/bin/codex`, installed from `@openai/codex@0.151.0`.

## Direct verification

A direct authenticated request used:

- Model: `gpt-5.6-luna`
- APICostX reasoning: `high`
- Sandbox: `read-only`
- Task: a report under 250 words with Summary, Benefits, and Risks sections

The live process command contained:

```text
-m gpt-5.6-luna -c model_reasoning_effort="xhigh"
```

The request completed successfully with a coherent three-section report.
Metering returned 12,741 prompt tokens, 327 completion tokens, 91 reasoning
tokens, and 8,960 cached prompt tokens.

## Validation

- Backend focused configuration suite: 40 passed.
- FilePromptForge tests: 8 passed.
- Searchbox and CodexExecAPI suite: 63 passed before final installation-doc update.
- Frontend ESLint and production build: passed.
- Backend aggregate isolated run: 306 passed; six environment-only failures were
  caused by runtime paths not mounted into the temporary test container.
