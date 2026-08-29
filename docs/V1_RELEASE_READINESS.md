# Truth Hunter 1.0 Release Readiness

Audit date: 2026-08-30

Status: **0.9.0-rc1 technically ready.** All engineering gates are implemented.
Independent review of the English and Hungarian legal language remains required
before the stability promise implied by version 1.0.

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

**Gate completed 2026-08-30.** A permanent encryption key is configured, the
Windows task runs daily at 03:00 with start-when-available behavior, its first
run returned success, and the resulting authenticated backup restored into the
guarded disposable database with matching user and investigation counts. Keeping
an additional encrypted copy off-host remains a strongly recommended resilience
improvement rather than a blocker for the initial single-server 1.0 release.

Acceptance gate:

- A scheduled encrypted backup is produced without exposing credentials.
- Old backups are removed according to configured retention.
- The latest backup restores into a disposable database and passes integrity
  checks.
- The procedure is documented and an operator can run it manually.

### 2. Public investigation abuse and cost controls

**Gate completed 2026-08-30.** PostgreSQL-backed privacy-safe limits protect
claim submission, investigation start, and reporting. A production Turnstile
widget restricted to `truth.abathur.hu` is deployed and verified server-side.

Acceptance gate:

- Add bounded request limits for claim creation, OCR, confirmation, and reports.
- Add a privacy-conscious bot challenge such as Turnstile to the expensive entry
  point, with test-mode support.
- Return localized `429`/challenge errors without consuming investigation credit
  or provider capacity.
- Document behavior when the limiter store is unavailable.

### 3. Privacy Policy and Terms of Service

**Engineering gate completed 2026-08-30; external review pending.** English and
Hungarian pages disclose the operator contact, processed data, purposes,
retention, processors/transfers, user rights, deletion, and the informational
nature of results. They are linked globally and from registration. Final
Hungary/EU legal review cannot be replaced by automated engineering work.

Acceptance gate:

- Publish English and Hungarian Terms and Privacy pages.
- State controller/contact details, data categories, purposes, retention,
  processors, user rights, deletion behavior, international transfers, and the
  informational/non-professional nature of verdicts.
- Link both pages from every public page and the registration flow.
- Have the final legal language reviewed for the Hungary/EU deployment.

### 4. Production browser security policy

**Gate completed 2026-08-30.** The application and Caddy emit a Turnstile-aware
Content Security Policy, HSTS, frame protection, referrer policy, permissions
policy, and MIME-sniffing protection, with automated assertions.

Acceptance gate:

- Add a tested CSP compatible with the current server-rendered templates.
- Add HSTS after confirming HTTPS-only operation and certificate renewal.
- Add automated header assertions for production proxy configuration.

### 5. Durable investigation recovery

**Gate completed 2026-08-30 for the documented single-server architecture.** On
startup, work owned by the previous process is moved to an explicit interrupted
terminal state without consuming a credit. Completed snapshots are idempotent
and cannot be overwritten by a duplicate completion call. Recovery behavior is
covered by integration tests.

Acceptance gate:

- Detect stale confirmed/running investigations at startup or by a periodic
  reconciler.
- Safely retry eligible work or mark it failed with a useful reason and no usage
  penalty.
- Make completion idempotent and cover restart recovery with tests.

### 6. PostgreSQL migration coverage in CI

**Gate completed 2026-08-30.** GitHub Actions starts PostgreSQL 17, runs the
normal suite with `TEST_DATABASE_URL`, upgrades a clean database to head, and
tests the upgrade path from the pre-release-candidate schema.

Acceptance gate:

- Start PostgreSQL as a CI service.
- Upgrade a clean database to migration head and run database integration tests.
- Test upgrade from the last released schema before tagging 1.0.

## Should improve for the release candidate

- Continue expanding the reviewed verdict regression corpus beyond the current
  true, false, mixed, inconclusive, medical, legal/technical, and documented-label
  cases to add more current-event, image-derived, and Hungarian examples.
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

1. ~~Complete backup/restore and verify it against production-shaped data.~~
2. ~~Add abuse protection and durable investigation recovery.~~
3. ~~Publish Terms/Privacy and harden browser headers.~~
4. ~~Enable PostgreSQL CI and expand the reviewed benchmark.~~
5. Run security, accessibility, mobile, restore, and live smoke checks.
6. Release `0.9.0-rc1`, obtain legal review, and collect focused beta feedback.
7. Fix release-candidate blockers, freeze behavior, and repeat every gate.
8. Set version `1.0.0`, update the changelog/readme/security policy, tag
   `v1.0.0`, publish the GitHub release, and deploy the tagged image.

## Current decision

The product is suitable for a public `0.9.0-rc1`. Do not tag stable `1.0.0`
until the legal language has been independently reviewed and release-candidate
smoke/accessibility checks have passed.
