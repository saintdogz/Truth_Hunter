# Changelog

All notable changes to Truth Hunter are documented in this file.

The project follows [Semantic Versioning](https://semver.org/). Truth Hunter is
currently a public beta, so behavior and interfaces may change before version 1.0.

## [Unreleased]

### Fixed

- Diversify generated search queries toward direct primary evidence,
  authoritative explanations, and credible limitations instead of generic topic
  searches.
- Conservatively skip dictionary definitions and unrelated generic homepages
  before spending source-evaluation capacity.
- Prevent neutral evidence or descriptions of a theory from appearing as
  strongest supporting or contradicting arguments.
- Stop secondary, unknown, and social sources that merely repeat speculative
  theories from counting as substantive supporting evidence.
- Make the permanent public share URL explicit after publishing so owners do not
  accidentally copy the private UUID route.
- Treat material prerequisites and exceptions as contradictions of unconditional
  claims instead of supporting a narrower interpretation.
- Prioritize authoritative regulatory evidence and preserve context around
  ambiguous acronyms in technical and legal searches.

### Added

- A prominent public-beta launch link in the README for visitors who want to test
  Truth Hunter without self-hosting it.
- Typed AI and search failure categories for rate limits, quota exhaustion,
  availability, authentication/configuration, invalid output, and payload limits.
- Retry policy that retries transient search failures but immediately falls back
  after permanent authentication or quota failures.
- A reviewed real-world regression corpus, beginning with the LAPL(A) passenger
  prerequisite claim.
- Localized, deterministic explanations showing why an investigation received
  Low, Medium, or High confidence.
- Actionable admin failure diagnostics that distinguish automatic recovery from
  owner-attention conditions without exposing sensitive provider details.

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
