# Contributing

Thanks for taking a look. This is how the project is developed locally and what
CI expects before a change lands.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Before you push

These are exactly the steps CI runs, so run them locally first:

```bash
ruff check .
mypy
pytest
```

CI runs the same on Python 3.11 and 3.12. `pytest` measures coverage of `app/`
and prints what is missing; CI runs the whole suite with `--cov-fail-under=70`,
so a change that adds code without tests turns the build red. The floor is not
applied locally, which keeps a single file or a `-k` selection usable while you
work — a partial run's coverage number says nothing about the project.

## Conventions

- **The core never knows which API it is talking to.** A new integration is a
  single new connector module plus an entry in `config.yaml`. If a change forces
  you to edit the orchestrator, storage, REST layer or CLI to add an API, the
  abstraction is wrong — fix the abstraction instead.
- **Async everywhere.** Connectors are `async`; use `httpx.AsyncClient`, never a
  blocking call inside the event loop. `pytest-asyncio` runs in `auto` mode.
- **Normalize at the edge.** A connector returns the unified schema; downstream
  code never special-cases a vendor's field names.
- **Types.** `app/` is type-checked with `mypy` (`disallow_untyped_defs`), so new
  functions need annotations.
- **Tests.** Add tests with the change; external HTTP is mocked with `respx`,
  never called for real.
- **Secrets.** API keys come from the environment. Never commit a key, and never
  put one in `config.yaml`.
- **Commits.** Short imperative subject, a body explaining the *why*.

## Reporting a security problem

Do not open a public issue — see [SECURITY.md](SECURITY.md).
