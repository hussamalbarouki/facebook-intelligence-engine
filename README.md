undefined
## v1.3.1 — runtime reliability fix

The API now runs Uvicorn as PID 1 directly. Chromium operates headlessly only
inside the browser fallback. The public API is independent of a virtual X display
and container starts do not need Xvfb. GitHub Actions validates `/healthz`
from an actual running Docker container before reporting a successful release.

If a preceding build caused HTTP 503, first restore the previous stable image
pinned by commit, then redeploy v1.3.1 after its GitHub Actions release succeeds.
