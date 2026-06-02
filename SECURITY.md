# Security Policy

Yours Sync Server is intended for self-hosted use.

## Supported Versions

Only the latest `main` branch and the latest published Docker image are supported.

## Reporting a Vulnerability

Please do not open public issues for secrets, authentication bypasses, or data exposure reports.

Send a private report through GitHub Security Advisories when available, or contact the maintainer through the repository profile.

## Operational Guidance

- Use a long random `YOURS_BACKUP_TOKEN`.
- Keep `.env` private.
- Prefer HTTPS for remote access.
- Back up the entire `data/` directory.
- Rotate the API key if a device or server is lost.
