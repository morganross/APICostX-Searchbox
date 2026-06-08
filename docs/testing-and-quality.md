# Searchbox Test Strategy and Quality Gates

We run a layered quality strategy inspired by common open-source engineering practice:

- Fast unit checks for determinism
- Property and fuzz-style checks for edge-case discovery
- Contract and integration checks for API stability
- Operational checks for reliability and security

Primary references:

- [Practical Testing Pyramid (Martin Fowler)](https://martinfowler.com/articles/practical-test-pyramid.html)
- [Hypothesis documentation](https://hypothesis.readthedocs.io/)
- [Pytest docs](https://docs.pytest.org/en/stable/contents.html)
- [OpenSSF Scorecard](https://securityscorecards.dev/)
- [OWASP API Testing Guide](https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/12-API_Testing/01-API_Reconnaissance)

## High-confidence test architecture

1. **Unit tests**
   - Deterministic helpers: parser extraction, query normalizers, URL/domain rules, text helpers, state store accessors, and budget calculations.

2. **Property-based tests**
   - Use [Hypothesis](https://hypothesis.readthedocs.io/en/latest/) for generated inputs:
     - parser output invariants
     - science-classifier normalization
     - config coercion and clamp behavior
     - URL/domain sanitization edge cases

3. **State and reliability tests**
   - , cooldown, and quota persistence behavior:
     - lock handling
     - atomic updates
     - snapshot consistency
     - recovery from corrupt state

4. **Contract tests**
   - API-level request/response contracts:
     -  science/non-science routing
     - 
     - 
     - 
   - Keep contract tests shape-focused for low-noise regressions.

5. **Fallback and routing tests**
   - Provider auto-fallback sequence
   - backoff and cooldown policies
   - quota block/limit behavior under repeated errors

6. **Integration tests**
   - Controlled mock providers and extractors with deterministic behavior
   - End-to-end orchestration tests for  and related paths

7. **Security-focused tests**
   - API risk coverage guided by [OWASP API Top 10](https://owasp.org/API-Security/editions/2019/en/0xa0-introduction-to-the-owasp-api-security-top-10/).
   - Credential handling, input validation, SSRF filtering, rate-limit enforcement, and secret masking.

8. **Mutation testing (opt-in)**
   -  /  on high-value modules to confirm tests catch behavioral defects.

9. **Load, stability, and chaos tests (opt-in)**
   - Load/soak checks for  and 
   - Provider outage and timeout fault-injection checks
   - Rate-limiting, queue, and disk-growth stress checks

10. **Property-driven API tests (opt-in, schema-aware)**
   - Tooling to evaluate API-level edge cases from schema/model specs
   - [Schemathesis](https://schemathesis.readthedocs.io/en/stable/) for schema-derived API property fuzzing

11. **Security and hardening automation**
   - Dependency and supply-chain scans:
     - [pip-audit](https://pypi.org/project/pip-audit/)
     - Secret scanning
     - CodeQL
     - [OpenSSF Scorecard](https://securityscorecards.dev/)

12. **Benchmark and regression performance tests (scheduled)**
   - Baseline response-time checks for key endpoints with scheduled probes

## Current suite mapping

- 
- 
- 
- 
-  (new): state + limits + parser + endpoint robustness contracts.

## Quality command matrix

Mandatory in PR gates:



Mandatory in CI image:



Optional and scheduled:



## Baseline results from latest run

- Full pytest suite: **47 passed**
- : **clean**
- : **passes**
- : **no known vulnerabilities found**
- : currently reports many existing typing issues (tracked as debt)
- : currently reports low-severity intentional handling warnings (tracked)

## CI guidance

- Make unit/property/contract/integration suites mandatory for every PR.
- Keep mutation/load/chaos/API-fuzz checks optional and scheduled until stable.
- Keep live-provider calls out of standard PR jobs; run those in dedicated release-candidate jobs.
- Keep  and  in the scheduled health smoke.
ing-imports searchbox tests
bandit -q -r searchbox
pytest -q --reruns 0
```

## Baseline results from latest run

- Full pytest suite: **49 passed**
- `ruff check .`: **clean**
- `python -m py_compile ...`: **passes**
- `pip-audit -r requirements.txt`: **no known vulnerabilities found**
- `mypy`: currently reports many existing typing issues (tracked as debt)
- `bandit`: currently reports no blocking issues; keep it as recurring hardening gate

## CI guidance

- Make unit/property/contract/integration suites mandatory for every PR.
- Keep mutation/load/chaos/API-fuzz checks optional and scheduled until stable.
- Keep live-provider calls out of standard PR jobs; run those in dedicated release-candidate jobs.
- Keep `/logs/...` and `/health/monitor` in the scheduled health smoke.
