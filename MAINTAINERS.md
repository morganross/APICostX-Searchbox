# Maintainers

Searchbox is maintained by the repository owner and contributors with merge access.

## Maintainer Responsibilities

- Keep CI passing.
- Review security-sensitive changes carefully.
- Require tests for provider behavior changes.
- Avoid committing secrets or private deployment details.
- Keep public docs aligned with runtime behavior.
- Prefer stable public contracts over internal churn.

## Release Responsibilities

Before cutting a release:

- CI passes.
- Secret scan passes.
- CodeQL is clean or findings are triaged.
- Changelog is updated.
- `.env.example` matches supported configuration.
- Public docs mention any breaking changes.
