# Public Abuse Protection

Truth Hunter protects expensive public workflows with two independent layers:

1. PostgreSQL-backed fixed-window limits survive application restarts.
2. Optional Cloudflare Turnstile validates a short-lived, single-use browser
   challenge before claim interpretation or OCR begins.

No raw IP address is stored in the rate-limit table. The application stores only
an HMAC-SHA256 digest derived from the action, client address, session/account
identity, and `APP_SECRET`. Expired buckets are pruned during normal use.

## Default limits

```dotenv
PUBLIC_RATE_LIMITS_ENABLED=true
CLAIM_SUBMISSION_LIMIT=10
INVESTIGATION_START_LIMIT=5
PUBLIC_REPORT_LIMIT=10
PUBLIC_LIMIT_WINDOW_SECONDS=3600
```

Production refuses to start if durable public limits are disabled. When the
database limiter is unavailable, protected work fails closed with a localized
`503` response. An exceeded limit returns a localized `429` without starting
provider work.

## Configure Cloudflare Turnstile

Turnstile is free and does not require the site to use Cloudflare DNS or proxying.
In the Cloudflare dashboard:

1. Create a Turnstile widget named `Truth Hunter claim submission`.
2. Allow only `truth.abathur.hu` as the production hostname.
3. Copy its public site key and private secret key into `.env`:

```dotenv
TURNSTILE_SITE_KEY=YOUR_PUBLIC_SITE_KEY
TURNSTILE_SECRET_KEY=YOUR_PRIVATE_SECRET_KEY
TURNSTILE_TIMEOUT_SECONDS=5
```

4. Recreate only the application container:

```powershell
docker compose up -d --no-deps --force-recreate truthhunter
```

5. Submit one claim from a private browser window and confirm that the Turnstile
   dashboard records a successful Siteverify request.

Truth Hunter validates every token with Cloudflare's Siteverify endpoint. In
production it additionally requires the returned hostname to equal
`truth.abathur.hu` and the widget action to equal `claim-submit`. Missing,
expired, reused, oversized, wrong-host, and wrong-action tokens are rejected.
Cloudflare test keys are explicitly rejected when `APP_ENV=production`.

If Turnstile itself is unreachable, claim submission fails closed with a
localized temporary-unavailability message; no search or AI work begins.

Official references:

- <https://developers.cloudflare.com/turnstile/get-started/>
- <https://developers.cloudflare.com/turnstile/get-started/server-side-validation/>
- <https://developers.cloudflare.com/turnstile/troubleshooting/testing/>
