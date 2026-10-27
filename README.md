undefined
## v1.3.1 — runtime reliability fix

The API now runs Uvicorn as PID 1 directly. Chromium operates headlessly only
inside the browser fallback. The public API is independent of a virtual X display
and container starts do not need Xvfb. GitHub Actions validates `/healthz`
from an actual running Docker container before reporting a successful release.

If a preceding build caused HTTP 503, first restore the previous stable image
pinned by commit, then redeploy v1.3.1 after its GitHub Actions release succeeds.

## v1.3.2 — Browser-first extraction and per-job live diagnostics

This version addresses a real production log pattern: Facebook loaded nine
GraphQL responses, but the extractor found no verifiable comments or reactors.

What changed:
- Browser-first (controlled by FB_BROWSER_FIRST=1, the default) tries real
  Facebook UI and its own GraphQL responses *before* costly 96-script doc-id
  discovery. If no verified interactions exist, legacy adapters remain available.
- Browser now attempts to open a post's comments entry first, then expands
  comment and reply controls in several languages. A reaction list is attempted
  only through recognized read-only controls.
- Browser GraphQL JSON parsing accepts more verified Comet comment shapes,
  nested body text and reactor IDs where Facebook omits profile URLs.
- Authenticated POST /v1/jobs/{job_id}/browser-diagnostics uses the existing
  server-side cookie vault, never user-supplied cookies. The result contains
  structural counters only: GraphQL response counts, count of comment-shaped
  nodes, comment/reaction container counts, DOM comment-link counts, open/expand
  action counts and login-wall classification. No bodies, Facebook names,
  tokens, cookies or screenshots are returned.
- A synthetic page is exercised inside the real Chromium binary during the
  Docker image build. This is a browser-level functional test, but **not a
  live authenticated Facebook extraction test**.

If diagnostic says no_interaction_payloads_observed, Facebook did not deliver
a recognizable comment/reaction container in the observed responses. It does
not establish that no comments exist. When it says
interaction_shapes_unrecognized, real interaction-shaped structures were
observed but our parser did not verify items, requiring schema-level adaptation.

We cannot extract actual Facebook cookies from prior screenshots, access your
Coolify secret vault externally, or make a live authenticated claim from CI.
The new protected diagnostic endpoint must run **on your server** to test the
actual session and the actual post.

Limits remain in place: 1 browser at once, 55-second bounded attempt, at most
100 comments and 100 reactors per browser attempt; no raw GraphQL responses
are logged or persisted.
