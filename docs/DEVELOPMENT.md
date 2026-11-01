# Development guide

This is the day-to-day loop for working on Truth Hunter outside Docker. For the containerized setup see the README; for operational runbooks see BACKUP_AND_RESTORE.md and ABUSE_PROTECTION.md.

## Prerequisites

- Python 3.10+
- PostgreSQL 14+ (a local instance or a disposable database via `TEST_DATABASE_URL`)
- Tesseract with `eng` and `hun` language data (native OCR only; the Docker image bundles it)

## First run

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env   # then edit values
alembic upgrade head
uvicorn app.main:app --reload
```

## Before every pull request

```powershell
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy app tests
```

The migration test is opt-in: `python -m pytest -m database` upgrades the database in
`TEST_DATABASE_URL`, so point it at a throwaway schema.

## Where things live

- `app/` — FastAPI application, routes, services, provider adapters
- `tests/` — unit, integration, and security tests (pytest markers select suites)
- `scripts/` — maintenance and backup utilities
- `searxng/` — search container configuration
- `docs/` — operator runbooks and release readiness notes
