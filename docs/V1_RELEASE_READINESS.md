# Truth Hunter 1.0 Release Readiness

Audit date: 2026-08-26

Status: **Not yet ready for 1.0.** The public beta is healthy and the core user
journey works, but the release-critical controls below must be completed before
the stability promise implied by version 1.0.

## Evidence reviewed

- Application, account, investigation, sharing, admin, OCR, search, and AI code.
- Docker Compose, Dockerfile, Caddy, migrations, CI, and public documentation.
- Full local quality suite: 129 passed, one optional PostgreSQL test skipped.
- Ruff, formatting, mypy, and Docker Compose validation passed.
- Production containers were healthy at audit time.
- Production had 67 investigations, seven registrations, no running jobs, and
  no application error/traceback log entries in the preceding 24 hours.
- Public liveness and readiness endpoints returned successfully.

## Must fix before 1.0

### 1. Automated encrypted backups and tested restoration

Implementation and a complete disposable restore drill are now complete. The
remaining operator gate is to configure a permanent encryption key, register the
Windows scheduled task, run it once, and retain an encrypted copy off-host.

Acceptance gate:

- A scheduled encrypted backup is produced without exposing credentials.
- Old backups are removed according to configured retention.
- The latest backup restores into a disposable database and passes integrity
  checks.
- The procedure is documented and an operator can run it manually.

### 2. Public investigation abuse and cost controls

PostgreSQL-backed privacy-safe limits are now implemented for claim submission,
investigation start, and public reporting, and the Turnstile integration is
implemented with mandatory server-side verification. The remaining operator
gate is to create a production Turnstile widget restricted to
`truth.abathur.hu`, configure both keys, deploy, and verify one real challenge.

Acceptance gate:

- Add bounded request limits for claim creation, OCR, confirmation, and reports.
- Add a privacy-conscious bot challenge such as Turnstile to the expensive entry
  point, with test-mode support.
- Return localized `429`/challenge errors without consuming investigation credit
  or provider capacity.
- Document behavior when the limiter store is unavailable.

### 3. Privacy Policy and Terms of Service

The About page explains privacy at a product level, but there are no dedicated
Terms or Privacy pages and no links in the footer. The service stores account
emails, claim text, evidence snapshots, provider audit data, feedback, and
reporter session identifiers in an EU operating context.

Acceptance gate:

- Publish English and Hungarian Terms and Privacy pages.
- State controller/contact details, data categories, purposes, retention,
  processors, user rights, deletion behavior, international transfers, and the
  informational/non-professional nature of verdicts.
- Link both pages from every public page and the registration flow.
- Have the final legal language reviewed for the Hungary/EU deployment.

### 4. Production browser security policy

The site sends `nosniff`, frame denial, referrer, and permissions policies, but
does not currently send HSTS or Content Security Policy headers.

Acceptance gate:

- Add a tested CSP compatible with the current server-rendered templates.
- Add HSTS after confirming HTTPS-only operation and certificate renewal.
- Add automated header assertions for production proxy configuration.

### 5. Durable investigation recovery

Investigations run as in-process background tasks. A process or host restart can
interrupt a job after confirmation and leave it without a final result. Version
1.0 must recover deterministically even if a full external queue is deferred.

Acceptance gate:

- Detect stale confirmed/running investigations at startup or by a periodic
  reconciler.
- Safely retry eligible work or mark it failed with a useful reason and no usage
  penalty.
- Make completion idempotent and cover restart recovery with tests.

### 6. PostgreSQL migration coverage in CI

The normal suite passes, but the database integration test is skipped unless
`TEST_DATABASE_URL` is configured. CI therefore does not continuously prove the
full migration chain against PostgreSQL.

Acceptance gate:

- Start PostgreSQL as a CI service.
- Upgrade a clean database to migration head and run database integration tests.
- Test upgrade from the last released schema before tagging 1.0.

## Should improve for the release candidate

- Expand the reviewed verdict regression corpus from two cases to a balanced
  collection covering true, false, mixed, inconclusive, scientific, medical,
  legal/technical, current-event, image-derived, English, and Hungarian claims.
- Define benchmark acceptance thresholds and record evaluator/search-plan
  versions with every expected result.
- Add automated accessibility checks and manually verify keyboard navigation,
  focus visibility, screen-reader landmarks, contrast, and mobile layouts.
- Add external uptime monitoring for `/health/live` and `/health/ready`, plus
  alerts for disk pressure, database growth, provider failure rate, and TLS
  certificate problems.
- Add dependency update/scanning automation and pin remaining production images
  or record an explicit update policy.
- Add a documented incident-response, rollback, and maintenance-mode procedure.
- Add moderation actions for public reports if the dashboard is intended to be
  the operational moderation interface.
- Define claim/evidence retention and an automated deletion schedule.
- Resolve the TestClient deprecation warning before its dependency becomes a
  breaking upgrade.

## Safe to postpone beyond 1.0

- Google authentication.
- Subscriptions, payments, credits, and premium plans.
- Evidence graphs and deep-dive multi-round investigations.
- Native mobile applications.
- A distributed job queue, provided deterministic restart recovery exists.
- Additional AI or search providers beyond the current abstractions.

## Release sequence

1. Complete backup/restore and verify it against production-shaped data.
2. Add abuse protection and durable investigation recovery.
3. Publish Terms/Privacy and harden browser headers.
4. Enable PostgreSQL CI and expand the reviewed benchmark.
5. Run security, accessibility, mobile, restore, and live smoke checks.
6. Release `0.9.0-rc1` and collect focused beta feedback.
7. Fix release-candidate blockers, freeze behavior, and repeat every gate.
8. Set version `1.0.0`, update the changelog/readme/security policy, tag
   `v1.0.0`, publish the GitHub release, and deploy the tagged image.

## Current decision

The product is suitable for continued public beta testing. It should not yet be
presented as a stable 1.0 release until all six must-fix gates pass.
