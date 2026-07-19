# Security Policy

## Supported Versions

| Version | Supported |
| ------- | --------- |
| 0.1.x   | ✅        |

## Reporting a Vulnerability

If you discover a security vulnerability, please **do not** open a public issue.
Instead, report it privately to the maintainer. You can expect an acknowledgement
within 72 hours and a remediation plan thereafter.

## Provider safety notes

- API keys are read from the environment (`OPENAI_API_KEY`,
  `OPENAI_BASE_URL`). Never commit credentials.
- The default `MockProvider` performs no network calls and sends no code
  off-device — safe for air-gapped CI.
- When using `OpenAIProvider`, function source is sent to the configured
  endpoint. Review what leaves your trust boundary.
