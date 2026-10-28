# Browser Login & Saved Facebook Profile — v2.1.0

**Purpose:** Stop exporting Facebook c_user/xs cookies manually. The user opens an HTTPS page on the same Coolify deployment, logs in to Facebook in an interactive Chromium browser, then saves/closes that browser. The read-only extraction engine subsequently opens the **same persistent Chrome profile**.

## Admin workflow
1. In Coolify, make sure `/data` is a persistent volume/mount. This is essential — the files must survive Redeploy and container recreation.
2. Confirm `/healthz` returns version `2.1.0` and the domain is HTTPS.
3. Open `https://dia.ee-link.info/browser-login` on mobile or desktop.
4. Enter the service's existing `API_KEY` on the page, then click 'فتح المتصفح الآمن'. The API key is sent only as an X-API-Key header over HTTPS and is not put in URLs or localStorage.
5. A graphical browser running on the VPS appears. Sign in to Facebook yourself and complete any MFA/checkpoint. Do not log out of Facebook.
6. Click 'حفظ الجلسة وإغلاق المتصفح'. The remote Chromium process is SIGTERMed gracefully, and its profile data are flushed to `/data/facebook-profile` before extraction is unlocked.
7. The server confirms `saved: true` only if the browser profile has both login cookies. This does NOT independently certify that Facebook will serve the desired post.
8. Test the previously failing Reel. Read `/v1/status` to confirm `saved_browser_profile: true` and `/v1/jobs/.../browser-diagnostics` for visible data after extraction.

## Technical architecture
- Internal Xvfb on `:99` starts with FastAPI; X11 has no TCP listener.
- `x11vnc` binds to `127.0.0.1:5901` **only while an admin login session is open**.
- The browser page loads the Debian-packaged noVNC client from `/browser-assets/core/rfb.js`.
- The VNC stream is forwarded by an authenticated FastAPI WebSocket `/v1/browser-session/stream`. No VNC port is published by Docker or Coolify.
- Admin session initiation requires the existing 32+ char API key and an exact matching `Origin`; a random temporary HttpOnly, Secure, SameSite=Strict cookie is used afterward.
- Browser session tokens never appear in a URL; no web login is captured in server logs, browser screenshots or recordings.
- Idle admin sessions expire after 20 minutes; hard cap 60 minutes. The background worker closes expired sessions and gracefully saves the browser profile.
- Only one Chromium profile owner at once. Extraction jobs remain queued while the admin login screen is active.
- Production extraction opens `launch_persistent_context(...,headless=False)` using exactly `/data/facebook-profile`, not a new headless context with separately injected cookies.
- If the profile has not been saved, the manual cookie-based extraction path remains available for migration.
- `FB_ENGINE=legacy` remains explicit emergency rollback only.

## Security and limitations
- Do not expose port 5901 or Xvfb publicly; expose only the existing HTTPS domain.
- Keep the `/data` mount private, backed up securely, and owned by the container's dedicated engine user. It contains sensitive logged-in browser state; it is not encrypted by the old CookieVault.
- Anyone who obtains your API key can start a login session. Rotate it if exposed.
- Never share API keys, passwords, MFA codes or cookies in the ChatGPT conversation.
- Facebook can invalidate sessions, require account challenges, or block automated browsers even when profile files persist. Profile persistence is testable; ongoing Facebook access is not guaranteed.
- After an actual Facebook logout, return to `/browser-login` and sign in again. Pressing Save & Close is NOT logging out.

## CI acceptance
- Python unit tests protect API authorization, cookie security and `FB_ENGINE` routing without manual cookie files.
- The Docker build tests real Chromium headed mode on Xvfb, saves a synthetic cookie to a profile, closes Chrome, launches a fresh process and verifies the cookie persists.
- Build and `/healthz` smoke checks must succeed before GHCR `latest` is pushed.
- The last acceptance step — actual Facebook access on the user's VPS and user account — must be tested interactively by the user.