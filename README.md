# Truth Hunter

Truth Hunter is a self-hosted evidence-investigation web application. This repository currently implements **Phases 1 through 3** of `TRUTH_HUNTER_SPEC.md`: the deployable foundation, provider-neutral investigation engine, and public investigation experience.

Version: **0.1.0**

## Implemented scope

Implemented:

- FastAPI application factory and server-rendered Jinja2 foundation
- Branded bilingual claim-submission homepage
- PostgreSQL connectivity through SQLAlchemy 2
- Alembic migration baseline
- Independent liveness and database-aware readiness endpoints
- Docker Compose services for the application, PostgreSQL, minimally configured SearXNG, and Caddy
- Basic security headers, trusted-host validation, safe configuration, tests, linting, formatting, and type checking
- English/Hungarian claim detection and strict claim/AI output schemas
- Replaceable AI and search protocols, with Groq, OpenAI, and official DeepSeek adapters, automatic operation-level fallback, and SearXNG integration
- Versioned prompts separating trusted instructions from hostile claim/source data
- SSRF-aware URL validation, redirect checks, timeouts, content limits, and bounded extraction
- Deterministic evidence weighting, sufficiency, confidence, conflict, and verdict rules
- Historical investigation, source, and evidence persistence
- A mocked end-to-end investigation pipeline integration test
- Session-bound CSRF protection for public forms
- Claim interpretation, confirmation, and one-time correction flow
- Background investigation execution with a polling progress experience
- Bilingual assessment pages with evidence balance, confidence, strongest arguments, conflict disclosure, methodology, and run metadata
- Server-side withholding of detailed evidence excerpts and source URLs until Phase 5 entitlements exist

Authentication, payments, credits, analytics, sharing, detailed source access, and other later-phase features are not implemented.

## Requirements

- Docker Desktop with Docker Compose (reference workflow)
- Optionally Python 3.10 or newer for native development

## Docker workflow (Windows PowerShell)

```powershell
Copy-Item .env.example .env
notepad .env
docker compose config
docker compose up --build -d
docker compose ps
Invoke-WebRequest http://localhost/health/live
Invoke-WebRequest http://localhost/health/ready
Start-Process http://localhost
```

Replace all `change-me` development values before any production deployment. The application container applies Alembic migrations before starting. PostgreSQL and SearXNG are internal-only; Caddy is the public entry point.

Real investigations require a valid `AI_API_KEY` for the selected `AI_PROVIDER`. Supported values are `openai`, `deepseek`, and `groq`. The recommended free-tier primary is Groq with `AI_MODEL=openai/gpt-oss-120b`. Optional `AI_FALLBACK_PROVIDER`, `AI_FALLBACK_API_KEY`, and `AI_FALLBACK_MODEL` values enable an automatic fallback after a sanitized primary-provider failure; all three must be configured together. The application can start and serve the homepage and health routes without a key; provider creation fails closed if an investigation is requested without one.

Inspect logs and shut down without deleting data:

```powershell
docker compose logs --tail 200 truthhunter postgres caddy searxng
docker compose down
```

`docker compose down -v` deletes database and service volumes and should only be used when that data is intentionally disposable.

## Native development

From PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

The default `DATABASE_URL` in `.env.example` addresses PostgreSQL by its Compose service name. For a native application process, either run PostgreSQL on a locally reachable port or change `DATABASE_URL` to the appropriate development database address. PostgreSQL is deliberately not published by the reference Compose configuration.

## Quality checks

```powershell
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy app tests
docker compose config --quiet
```

The PostgreSQL migration integration test is opt-in because it upgrades the configured database. Point `TEST_DATABASE_URL` at a disposable PostgreSQL database before running it:

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://user:password@host:5432/truthhunter_test"
python -m pytest -m database
```

All other tests run without PostgreSQL. The readiness tests replace the database probe at the FastAPI dependency boundary.

## Database migrations

```powershell
docker compose exec truthhunter alembic current
docker compose exec truthhunter alembic upgrade head
docker compose exec truthhunter alembic downgrade -1
docker compose exec truthhunter alembic revision --autogenerate -m "describe change"
```

Every schema change must be represented by an Alembic migration. Phase 1 creates the baseline, Phase 2 adds the `investigations`, `sources`, and `evidence` snapshot tables, and Phase 3 records one-time claim correction state.

## Health endpoints

- `GET /health/live` checks only that the application process is serving requests.
- `GET /health/ready` checks PostgreSQL connectivity and returns `503` with a sanitized response when unavailable.

## Configuration and security notes

- `.env` is excluded from Git and Docker build context.
- Production startup rejects the documented placeholder application secret.
- Application and Caddy responses include baseline security headers.
- The application runs as an unprivileged container user.
- PostgreSQL and SearXNG have no published host ports.
- Debug documentation endpoints are disabled when `APP_ENV=production`.
- Fetching blocks non-public address ranges and internal hostnames, revalidates redirects, bounds time/size/redirects, checks content types, and ignores environment proxies. Further production SSRF hardening remains in Phase 8.
- Backup/encryption, rate limiting, authentication security, and provider-specific production hardening remain in their specification phases.

The product specification remains authoritative: [`TRUTH_HUNTER_SPEC.md`](TRUTH_HUNTER_SPEC.md).
