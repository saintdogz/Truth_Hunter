# Changelog

All notable changes to Truth Hunter are documented in this file.

The project follows [Semantic Versioning](https://semver.org/). Truth Hunter is
currently a public beta, so behavior and interfaces may change before version 1.0.

## [Unreleased]

### Fixed

- Treat material prerequisites and exceptions as contradictions of unconditional
  claims instead of supporting a narrower interpretation.
- Prioritize authoritative regulatory evidence and preserve context around
  ambiguous acronyms in technical and legal searches.

## [0.1.0] - 2026-08-24

### Added

- Evidence-based claim investigations with confirmation before processing.
- English and Hungarian interfaces with translated investigation results.
- Free-first AI routing through Groq and Gemini, with an optional DeepSeek fallback.
- SearXNG evidence discovery with an optional Brave Search API fallback.
- Deterministic verdict scoring with visible uncertainty and supporting sources.
- Image upload and clipboard paste support for OCR-assisted claim extraction.
- Account registration, email verification, password reset, history, and deletion.
- Public result sharing, user feedback, and an operational admin dashboard.
- Health and readiness endpoints, Docker Compose deployment, and Caddy HTTPS support.
- Public documentation, contribution guidance, security policy, and MIT license.

### Security

- Server-side request forgery protections for fetched evidence URLs.
- Prompt-injection defenses for untrusted source material.
- CSRF protection, rate limiting, secure password hashing, and signed sessions.
- Uploaded images are validated, processed transiently, and not retained.

### Known limitations

- Investigation quality depends on accessible search results and source quality.
- Provider quotas, rate limits, and outages can prevent an investigation from completing.
- OCR accuracy depends on image clarity and text layout.
- Verdicts are informational assessments, not guarantees or professional advice.

[0.1.0]: https://github.com/saintdogz/Truth_Hunter/releases/tag/v0.1.0
