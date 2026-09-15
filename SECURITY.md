# Security policy

The guard is a safety net against agent mistakes, not a security boundary. Internal errors and analysis timeouts fail open.

## Worth reporting

- A command [docs/guard-coverage.md](docs/guard-coverage.md) says is refused, but is allowed. Check [tests/redteam-candidates.txt](tests/redteam-candidates.txt) first; listed gaps are deliberate.
- A crash or hang on a shape a rule clearly covers.

A person or agent deliberately working around the guard is not a vulnerability.

## How to report

Use GitHub private vulnerability reporting: **Security**, then **Report a vulnerability**. Include the exact command, the working directory, and what you expected. Do not open a public issue for a working bypass.

Fixes ship in the latest release only.
