# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Everything below is on `main` and not yet tagged. The `/collect` change is
**breaking** for existing HTTP clients, so the next release is a major one.

### Security

- **`POST /collect` now requires an API key.** The endpoint had no
  authentication at all, and every selection it accepts becomes an outbound
  request from the server — so anyone who could reach the port could aim the
  process at whatever the connectors resolve. It now demands the secret from
  `UNIFIED_API_KEY` in an `X-API-Key` header. An unset key closes the endpoint
  (`503`) instead of opening it, so a deployment that forgets to configure one
  fails safe.
- **`POST /collect` caps a request at 25 connector selections.** The list was
  unbounded, which made one request an amplifier for as many upstream fetches
  as the caller cared to ask for.
- **CI fails on a credential committed anywhere in history.** A new job checks
  out the full history and greps every commit for private key blocks, AWS,
  GitHub, Slack and Google token shapes, and long values assigned to
  secret-sounding names. Deleting a leaked secret from the tip does not un-leak
  it, so the tip alone was never enough to check.
- **The security scans re-run weekly.** bandit and pip-audit only know the
  advisories that existed when they last ran; a Monday cron re-checks the same
  tree against a current database rather than letting a green badge go stale.
- **Key and certificate material is git-ignored** — `*.pem`, `*.key`, `*.p12`,
  `*.pfx`, `*.crt`, `id_rsa*`, `credentials.json`.
- Dependency floors were raised past releases with published CVEs.
- bandit and pip-audit run on every push.
- Every GitHub Action is pinned to a full commit SHA, and the workflow token is
  scoped to `contents: read`.

### Added

- `.env.example`, documenting all four `UNIFIED_` variables the platform reads
  with their defaults. The README had linked to this file since the first
  release; the file itself had never been committed, so the link 404'd.
- A security policy and a contributing guide.
- This changelog.

### Changed

- **Coverage is a gate, not a guess.** `pytest` now measures coverage of `app/`
  on every run and fails below 70%; nothing had been measuring it at all.
- Repository links point at the kebab-case repository name.
- CI upgrades setuptools before pip-audit runs, so the runner's own build
  tooling cannot fail the audit.
- Dependabot's grouped action updates.

### Fixed

- The MIT notice and the package metadata now both name the copyright holder
  in full; they previously disagreed with each other and with the history.
- A `.mailmap` collapses the two spellings of the sole author, which had made
  the repository look like it had two contributors.

## [1.0.0] - 2026-07-22

First release.

### Added

- The platform: pluggable connectors behind one `BaseConnector` interface,
  concurrent collection with `asyncio.gather`, a single `UnifiedRecord` schema,
  async SQLite persistence with idempotent upserts, and a TTL cache.
- Resilience for every outbound call — retry with exponential backoff and
  jitter, token-bucket rate limiting, and a per-connector circuit breaker.
- Weather, crypto and GitHub connectors, none of which require a key.
- Two interfaces over the same core: a FastAPI REST API and an argparse CLI.
- Structured JSON logging and in-memory metrics at `/metrics`.
- A `Dockerfile` and `docker-compose.yml`.
- CI running ruff, mypy and pytest on Python 3.11 and 3.12.
- The MIT license.

[Unreleased]: https://github.com/mojtaba-py-code/unified-api-integration-platform/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/mojtaba-py-code/unified-api-integration-platform/releases/tag/v1.0.0
