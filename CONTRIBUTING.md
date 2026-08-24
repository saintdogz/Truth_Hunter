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

## Adding an AI provider

1. Implement the `AIProvider` protocol in `app/ai/base.py`. Providers must return
   the existing validated Pydantic models and must never decide the final verdict.
2. Prefer the shared `StructuredChatProvider` adapter when the service supports an
   OpenAI-compatible structured-output API.
3. Map provider failures to the sanitized types in `app/ai/errors.py`. Never log
   API keys, raw response bodies containing user data, or hidden reasoning.
4. Register the provider in `app/ai/factory.py` and expose only non-sensitive
   configuration in `.env.example`.
5. Add unit tests for successful structured output, malformed output, rate limits,
   quota exhaustion, authentication failure, fallback order, and cooldown behavior.

Free providers belong before paid providers. Paid fallback must remain explicitly
enabled and bounded; a new provider must not bypass those controls.

## Adding a reviewed regression case

Add a sanitized fixture to `tests/regression/cases.json` only after checking the
claim against authoritative sources. Include the review date, expected verdict,
expected confidence, and representative structured evidence. Do not include user
identifiers, private investigation links, or copyrighted full-page content.
