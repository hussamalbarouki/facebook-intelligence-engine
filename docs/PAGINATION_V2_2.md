# v2.2.0 — Comment pagination and reaction listing

## Root cause of returning exactly 20 comments
Facebook commonly delivers comments in batches; the previous implementation only tried 8 scroll passes and repeatedly called a generic 'open comments' function, potentially re-clicking the comments entry instead of loading the next page. It neither confirmed a new batch nor followed visible UI pagination.
A separate, independent issue is the requested per-job comments_limit. If PHP sends comments_limit=20, returning 20 is correct. The engine does not override explicit limits. Inspect GET /v1/jobs/{id} for the stored limit.

## Changes
- Collect comment IDs from both Facebook GraphQL responses and the current browser DOM after each pass.
- Scroll the nearest visible comment-pane scrollable ancestor. For virtualized UI, retain all unique IDs even if previous DOM elements disappear.
- Click only explicitly labeled 'View more comments / replies' controls within an open comments dialog, not the initial drawer opener repeatedly.
- Stop when the requested/effective limit is reached, 5 passes produce no new comments, 80 scroll passes are attempted, or the total 150-second budget is reached.
- Report visible comment ID count, unique returned count, cursor presence (without cursor values), number of UI scroll passes, expansion clicks, and stop reason.
- Optional reaction-list opening only via explicit read-only people-who-reacted / reaction-count UI or verified reaction-list link. Like and aria-pressed toggle elements are excluded. For videos where Facebook does not expose named reactors, return a partial result with reason no_verified_reactor_list_control.
- Internal caps 500 comments and 300 reactor identities per attempt. These are not claims of completeness; unreadable/deleted/private content cannot be recovered.
- The protected browser diagnostics endpoint includes the pagination measurements, but never returns cookies, raw network payloads or arbitrary user text.

## Acceptance tests
The Docker image build executes tests/pagination_smoke.py inside real Chromium using local synthetic UI: 20 initial comments, 20 appended on scroll, another 20 on a View more click, and an explicit people-who-reacted dialog with a single verifiable profile. The test asserts the Like button is never clicked.
This is a **local synthetic test**, not a verified Facebook live extraction against the saved Coolify login. GitHub Actions cannot access the user's private Chrome profile.

## Deployment / verify
1. Redeploy the published GHCR :latest image manually in Coolify. Do not Restart without pulling.
2. Confirm /healthz version 2.2.0 and persistent /data/profile.
3. Submit the SAME reel with comments_limit=200, reactors_limit=100 to ensure PHP is not explicitly stopping at 20.
4. Fetch /v1/jobs/{job_id}/result and inspect coverage comments_effective_limit, comments_stop_reason, comment_scroll_passes, comment_expansion_clicks, reactions_list_opened and reactors_stop_reason.
5. If only 20 are returned, run POST /v1/jobs/{job_id}/browser-diagnostics and inspect non-sensitive UI and GraphQL response counters.
6. If comments stop at 20 with no new UI results, Facebook may be serving only that subset to the profile; a separate provider with cursor pagination may be required. Do not assume all reactions' identities can be retrieved.