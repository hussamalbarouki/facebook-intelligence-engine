# Facebook Intelligence Engine v1.0 — API-first / Docker / Coolify

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