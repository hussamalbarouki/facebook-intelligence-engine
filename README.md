# Facebook Intelligence Engine v1.3.0 — Hybrid Browser + GraphQL / Docker / Coolify

A self-hosted REST API wrapper around the **unofficial** `kevinzg/facebook-scraper` library. Designed for a PHP admin dashboard on cPanel and a disposable Coolify VPS. **There is no Facebook login bypass or official Meta API.** Facebook may restrict scraping and may not reveal full reaction lists; treat returned lists as *partial* and use only data you are permitted to access.

## Features

- Container image built on GitHub Actions → GHCR → Coolify (no Python setup on VPS)
- Job queue with SQLite persistence, idempotency ID, status, retry, cancel, pagination
- Admin REST API for Facebook Cookies, settings, metrics, audit history, engine capabilities
- Cookies encrypted at rest via Fernet using an auto-generated key on the `/data` volume; values **never exposed** in GET responses
- One worker to avoid excessive concurrent Facebook requests, cleanup and cooldown controls
- OpenAPI Swagger `/docs`, OpenAPI JSON `/openapi.json`, PHP 8.1+ server-side SDK
- `GET /healthz` without credentials; all `/v1/*` require `X-API-Key`

## Quick start

Public Docker image after successful GitHub Actions publication + GHCR package public setting:

```
ghcr.io/hussamalbarouki/facebook-intelligence-engine:latest
```

**Coolify:** New → Docker Image → enter reference → internal port **8000** → persistent volume at **/data** → runtime variable `API_KEY` (random 32+ chars) → HTTPS domain → Deploy.

**Manage Facebook session from your own PHP panel**, without changing the image:

```http
PUT /v1/facebook/cookies
X-API-Key: YOUR_MASTER_KEY
Content-Type: application/json

{"cookies":{"c_user":"...","xs":"..."}}
```

`GET /v1/facebook/cookies` reports configuration/last update, never cookie values. Use `DELETE` to remove. More than two cookies can be imported as a name/value map or JSON export array. **Never put cookies, PHP API keys, or real sessions in GitHub or front-end JavaScript.**

### Documentation

- [Exact Coolify deployment (Arabic)](docs/COOLIFY-AR.md)
- [Full management and job API (Arabic)](docs/API-AR.md)
- [VPS disaster recovery (Arabic)](docs/RECOVERY-AR.md)
- [Server-only PHP SDK](php/src/FacebookEngine.php)

### Self-test

```bash
python -m unittest discover -s tests -v
```

The included tests **mock Facebook**: they verify local API, encrypted cookie storage, and job flow, but not Facebook connectivity or complete extraction. The upstream scraper commit is pinned and may be outdated.

## Security baseline

Use HTTPS, long `API_KEY`, never expose it in browser, never publish browser cookies, limit the domain/port access if possible, and protect the PHP admin dashboard with authentication and CSRF defenses. Store `/data` backups off the VPS; a volume is **not a backup**. Treat reactor names/profile URLs as personal data and minimize their retention.
## v1.3.0 — Hybrid browser + lightweight GraphQL

The existing FastAPI endpoints, PHP dashboard and encrypted session vault remain compatible.

Extraction now uses layered adapters:
1. Resolve opaque Facebook share links to the post permalink.
2. Try lightweight GraphQL, without using fabricated doc IDs.
3. Try the legacy HTML adapter when markup remains accessible.
4. When those fail, use a browser fallback that observes the GraphQL responses Facebook
   serves to that browser and reads verifiable rendered comment permalinks.
5. Report only verifiable items, always with partial coverage, otherwise fail the job.

Browser fallback implementation (Playwright 1.64.1 / Chromium / Xvfb):
- Environment variable FB_BROWSER_ENABLED=1 is enabled in the published Docker image;
  set FB_BROWSER_ENABLED=0 in Coolify to switch it off.
- Single browser at a time, one worker, bounded 55-second attempt.
- Up to 100 observed comments and 100 observed reactors per browser attempt.
- Media/fonts are blocked to conserve RAM and bandwidth on smaller VPS hosts.
- Only explicit read-only expand-comments and reaction-list controls are clicked;
  no Like, Follow or Reply action is automated.
- No browser screenshots, raw responses, cookies, or access tokens are retained;
  cookies remain in encrypted /data storage and are deleted from temporary files.
- A 4 GB RAM, 2 vCPU VPS is a practical starting point; monitor resource usage.

Deploy: wait for GitHub Actions to complete tests, build and Chromium launch smoke test;
Redeploy in Coolify using the same GHCR latest image. Restart alone is insufficient.
Check /healthz for 1.3.0. Existing PHP configuration and cookies need no change.

Important: automated browser observation is still subject to Facebook's access
restrictions and to what the authenticated user is allowed to view. No guarantee
is made that all reactors, reply threads, or comments will be available. No live
Facebook extraction test is run in GitHub Actions.
