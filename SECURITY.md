# Security Policy

## Supported versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

Security fixes are applied to `main` and released from there.

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Report it privately through GitHub's
[Report a vulnerability](https://github.com/mojtaba-py-code/unified-api-integration-platform/security/advisories/new)
form, or by email to **mojtaba.python@gmail.com**.

Include what you can:

- the affected version, tag or commit,
- what the issue is and what an attacker gains from it,
- steps or a minimal proof of concept that reproduces it.

## What to expect

- Acknowledgement within **72 hours**.
- An initial assessment within **7 days**.
- A fix and a published advisory once a patch is ready.
- Credit in the advisory, if you want it.

## Scope

In scope: the code in this repository — the REST API, the CLI, the connectors
that talk to external services, the normalization layer that handles their
responses, and the storage layer.

Out of scope:

- Vulnerabilities in third-party dependencies or in the external APIs this
  project integrates with — report those upstream; if this project's use of them
  is what makes them exploitable, that *is* in scope.
- Findings that require an attacker to already control the host or the process.

## Notes for operators

- API keys are read from the environment. `config.yaml` describes *which*
  connectors run, never their credentials — do not put a key in it, and do not
  commit a populated `.env`.
- An external API's response is untrusted input. It is normalized before it is
  stored; treat any new field the same way.
- The platform fans out to remote hosts on request. `POST /collect` — the only
  endpoint that does — requires the shared secret in `UNIFIED_API_KEY`, sent as
  `X-API-Key`, and refuses every request with `503` while that variable is
  unset. One request may name at most 25 connector selections, so a single call
  cannot fan out without bound. The rest of the API is read-only.
- Those are process-level controls, not a network boundary. If you expose the
  service publicly, still restrict which hosts the connectors may reach so it
  cannot be used as a proxy into your internal network.
