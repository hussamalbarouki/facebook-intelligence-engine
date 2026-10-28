# Facebook Read-Only Engine v2.0.0

This replaces the production extraction runtime, rather than patching GraphQL doc ID discovery.

## Architecture
- app/read_only_v2.py owns browser startup, scoped cookies, navigation, hydration, comment drawer, scrolling, data parsing, normalization, output and diagnostics.
- app/engine.py::scrape_post routes production jobs to v2 by default, preserving FastAPI endpoints and the PHP dashboard.
- Older GraphQL and HTML code remains available only via FB_ENGINE=legacy as an explicit emergency rollback.
- One browser at a time. Bounded attempts. Results marked partial; counts alone are not reported as extracted identities.
- No Facebook session material or raw GraphQL response is logged or sent back.

## Languages
Comment extraction is structurally language-independent: author links, comment_id permalink links, Unicode text nodes and GraphQL fields.
Navigation-label coverage includes Arabic, English, French, Hindi, Urdu (Pakistan), Bengali, Punjabi in Gurmukhi and Shahmukhi, Pashto, Sindhi, Nepali, Tamil, Telugu, Marathi, Gujarati, Malayalam, Kannada, Odia, Sinhala, Burmese, Spanish, Portuguese, Italian, German, Turkish, Indonesian, Russian, Ukrainian, Japanese, Korean, Chinese, Thai, Vietnamese, Persian, Hebrew, Swahili, Dutch, Polish and Swedish.
These labels are not a guarantee: Facebook can change localized UI and A/B variants. The parser does not translate or modify a person's original comment text.

## Safety
The V2 runtime does not implement posting, liking, replying or following. It never intentionally clicks a state-changing reaction control.
Only read-only comment-list and expand controls are candidates. The French Commenter button is accepted on Reels/videos because an actual signed-in browser test proved it opened a comment drawer.
Reaction names may be unavailable even if aggregate reaction counts are public.

## Authenticated live browser evidence
Target: https://www.facebook.com/reel/1418347453748116
Using a separately connected signed-in Facebook profile, the French Commenter control opened a side panel with two visible comments and their exact comment_id permalinks.
This browser observation proves the user-visible route exists. It is NOT a successful end-to-end test of this new Docker engine using the separate Coolify cookie vault.
A previous exploratory agent accidentally toggled the Like control. The V2 engine explicitly does not interact with Like controls.

## Deployment
1. Verify GitHub Actions unit tests, built-image Chromium DOM smoke and running-container health smoke succeed.
2. The workflow only pushes Docker image latest after passing all smoke tests.
3. Manually Redeploy Coolify with the unchanged DATA_DIR=/data volume and API_KEY.
4. Verify /healthz reports 2.0.0, then test the original share/v URL.
5. For any failure run the authenticated POST /v1/jobs/{id}/browser-diagnostics on the same job. It reports safe aggregated UI and GraphQL metrics.

## Prior art reviewed
- https://github.com/brightpx/fbcommentviewrt (MIT): architecture for separate read-only browser, navigator and parser. Its unmodified group-post parser requires /user/ authors and is not a suitable drop-in Reel solution.
- https://github.com/kevinzg/facebook-scraper (MIT): older HTML-based extraction engine, retained for explicit rollback.
- https://github.com/XD-MHLOO/facebook-gql-scraper (MIT): GraphQL operation discovery, retained for explicit rollback.
Commercial actors such as Apify may not expose their internal scraper code for copying.

## Important limitation
Only an authenticated test against the user's Facebook Reel and the actual server-side session can prove this version extracts individual comments. No available method can guarantee access to all users who reacted when Facebook does not expose their identities.