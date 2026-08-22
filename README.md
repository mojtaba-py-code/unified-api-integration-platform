# Unified API Integration Platform

A production-style platform that connects to **multiple external APIs concurrently**, normalizes their wildly different responses into **one unified schema**, and stores them — all behind a single interface exposed as both a **REST API** and a **CLI**.

The whole design rests on one idea: **the core never knows which API it is talking to.** Every API is a self-contained *connector*, so adding a new integration is a single new file — nothing in the orchestrator, storage, API, or CLI changes.

[![CI](https://github.com/mojtaba-py-code/unified-api-integration-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/mojtaba-py-code/unified-api-integration-platform/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](https://www.python.org)
[![Typed](https://img.shields.io/badge/typed-mypy-2A6DB2.svg)](https://mypy-lang.org/)
[![Ruff](https://img.shields.io/badge/style-ruff-D7FF64.svg)](https://docs.astral.sh/ruff/)
[![Security](https://img.shields.io/badge/security-bandit%20%2B%20pip--audit-4B8BBE.svg)](SECURITY.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Features

- 🔌 **Pluggable connectors** — one interface (`BaseConnector`); register a new API in one line.
- 🔄 **Unified schema** — every source is mapped to a single `UnifiedRecord` shape.
- ⚡ **Concurrent collection** — all connectors fetched in parallel with `asyncio.gather`.
- 🛡️ **Real resilience** — retry with exponential backoff + jitter, token-bucket rate limiting, and a per-connector circuit breaker.
- 🗄️ **Persistence + cache** — async SQLite storage with idempotent upserts, plus a TTL cache to avoid redundant calls.
- 📊 **Observability** — structured JSON logging and in-memory metrics (`/metrics`).
- 🔐 **Safe config** — non-secret settings in `config.yaml`; secrets (e.g. a GitHub token) only via env / `.env`.
- ✅ **Fully tested offline** — every test mocks the network; CI runs ruff + mypy + pytest on 3.11 & 3.12.
- 🐳 **Container-ready** — `Dockerfile` + `docker-compose.yml`.

## Bundled connectors (all free, no key required)

| Connector | Source | Record type |
|-----------|--------|-------------|
| `weather` | [Open-Meteo](https://open-meteo.com) | current weather |
| `crypto`  | [CoinGecko](https://www.coingecko.com) | crypto prices |
| `github`  | [GitHub REST API](https://docs.github.com/rest) | repository stats |

## Architecture

```
        ┌──────────────┐   ┌──────────────┐
        │  REST API    │   │     CLI      │      interfaces
        │  (FastAPI)   │   │  (argparse)  │
        └──────┬───────┘   └──────┬───────┘
               └────────┬─────────┘
                 ┌───────▼────────┐
                 │  Orchestrator  │  concurrent fetch + cache + persist
                 └───────┬────────┘
        ┌────────────────┼────────────────┐
   ┌────▼────┐      ┌────▼────┐       ┌────▼────┐
   │ weather │      │ crypto  │       │ github  │   connectors (BaseConnector)
   └────┬────┘      └────┬────┘       └────┬────┘
        └───── ResilientHttpClient ────────┘        retry · rate-limit · breaker
                 ┌───────▼────────┐
                 │   Normalizer   │  → UnifiedRecord
                 └───────┬────────┘
             ┌───────────┴───────────┐
        ┌────▼─────┐            ┌─────▼─────┐
        │ SQLite   │            │ TTL Cache │
        └──────────┘            └───────────┘
```

## Quickstart

```bash
# 1. Install (a virtualenv is recommended)
pip install -e ".[dev]"

# 2. Collect from every enabled connector and store the results
python -m app collect

# 3. Inspect what was stored
python -m app list --limit 10

# 4. Or run the HTTP API and open the interactive docs at /docs
python -m app serve
```

## CLI

```bash
python -m app connectors                 # list available connectors
python -m app collect                    # collect from all enabled connectors
python -m app collect --connector crypto # collect from a single connector
python -m app list --source github       # query stored records
python -m app serve --port 8000          # run the REST API
```

## REST API

| Method | Path          | Description                              |
|--------|---------------|------------------------------------------|
| GET    | `/health`     | Liveness probe                           |
| GET    | `/connectors` | List available connectors                |
| POST   | `/collect`    | Trigger a collection run                 |
| GET    | `/records`    | Query stored records (`source`, `record_type`, `limit`) |
| GET    | `/metrics`    | Counter snapshot                         |

```bash
# Trigger a collection for specific connectors with custom params
curl -X POST http://localhost:8000/collect \
  -H 'Content-Type: application/json' \
  -d '{"selections": [{"connector": "crypto", "params": {"ids": ["bitcoin"], "vs_currency": "eur"}}]}'
```

Interactive OpenAPI docs are served at **`/docs`**.

## Adding a new connector

1. Create `app/connectors/mysource.py` subclassing `BaseConnector`; implement `fetch()` to return `list[UnifiedRecord]`.
2. Register it in `app/connectors/registry.py` (`CONNECTOR_TYPES`).
3. Add it under `connectors:` in `config.yaml`.

That's it — no other file changes.

## Configuration

Non-secret settings live in [`config.yaml`](config.yaml): HTTP timeouts, retry/rate-limit/circuit-breaker tuning, cache TTL, and per-connector base URLs.

Secrets and per-environment overrides come from the environment instead — every one of them is prefixed `UNIFIED_` and documented in [`.env.example`](.env.example):

```bash
cp .env.example .env   # then fill in what you need; .env is git-ignored
```

| Variable | Purpose | Default |
|----------|---------|---------|
| `UNIFIED_GITHUB_TOKEN` | Lifts the GitHub connector's rate limit from 60 to 5000 req/h | unset (anonymous) |
| `UNIFIED_CONFIG_PATH` | Path to the YAML settings file | `config.yaml` |
| `UNIFIED_DATABASE_PATH` | Overrides `app.database_path` from the YAML | `data/unified.db` |

## Development

```bash
ruff check .   # lint
mypy           # type-check
pytest         # run the offline test suite
```

## Docker

```bash
docker compose up --build      # API on http://localhost:8000
```

## Project layout

```
app/
├── core/         # config, logging, metrics, exceptions
├── resilience/   # retry, rate limiter, circuit breaker, HTTP client
├── connectors/   # BaseConnector + weather / crypto / github + registry
├── normalize/    # the UnifiedRecord schema
├── storage/      # async SQLite repository
├── cache/        # TTL cache
├── orchestrator.py  # concurrent collection engine
├── platform.py      # wires everything together
├── api/          # FastAPI app
└── cli.py        # command-line interface
tests/            # fully offline (network mocked)
```

## License

MIT
