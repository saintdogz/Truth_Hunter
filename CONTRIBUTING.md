# Contributing to Truth Hunter

Truth Hunter is an early-stage evidence-investigation project. Small, focused
changes with clear tests are welcome.

## Development workflow

1. Fork the repository and create a focused branch.
2. Copy `.env.example` to `.env` and use development-only credentials.
3. Start the stack with `docker compose up --build -d`.
4. Add or update tests for meaningful behavior.
5. Run the complete quality checks before opening a pull request.

```powershell
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy app tests
docker compose config --quiet
```

## Project rules

- Treat claims, fetched pages, and uploaded files as hostile input.
- Never commit `.env`, credentials, user data, or production exports.
- Keep verdict scoring deterministic and outside unrestricted model output.
- Preserve AI and search provider abstractions.
- Keep changes consistent with `TRUTH_HUNTER_SPEC.md` or explain the required
  specification revision.
- Do not expose private chain-of-thought.

For vulnerabilities, follow `SECURITY.md` instead of opening a public issue.
