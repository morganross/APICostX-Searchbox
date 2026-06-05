# Security Policy

Searchbox handles provider keys and fetches external URLs. Treat public deployments as internet-facing services.

## Supported Versions

Security fixes target the latest released version and the main development branch.

## Reporting a Vulnerability

Open a private security advisory on GitHub if available, or contact the maintainers through the repository's published security contact.

Please do not disclose working exploits publicly before maintainers have had a reasonable chance to respond.

## Important Security Expectations

- Do not commit `.env` files or provider keys.
- Do not log API keys, authorization headers, raw prompts, or raw model outputs.
- Enable auth before exposing Searchbox to the public internet.
- Keep private IP fetch blocking enabled for untrusted users.
- Keep provider quotas conservative.
