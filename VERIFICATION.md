# Verification report ? 11 October 2026

## Scope

Existing FastAPI, React design, MongoDB, Open-Meteo/ERA5 flow and heatwave definition retained. No GitHub push, repository creation or public deployment performed.

## Bugs found and fixed

- Geocoding identity became ambiguous after selection because state/country were hidden. Full labels now remain visible; each selectable suggestion includes its source ID-linked identity, coordinates and place/reference-point kind. Invalid upstream coordinates are filtered. Search qualifiers are no longer discarded, and stale requests cannot override a newer selection. Custom coordinates clear the previous place identity. Scope explicitly states single ERA5 grid cell, not a whole-state or area average.
- The live suspicious result is Bih?r, Uttar Pradesh, India, GeoNames ID 10470188, coordinates 27.29201, 79.32543. It is a real same-named populated place, not the Indian state of Bihar. Search can also return same-named places in other countries. See `verification/live-results.json` for actual source records.
- Analysis cache keys previously omitted baseline, algorithm version and source configuration. New keys include all of them. Raw-weather keys include source settings. Expired analysis rows are excluded even before MongoDB TTL cleanup. Legacy cache keys are bypassed. Coordinates intentionally round to three decimals consistently; differences below that precision can share a key.
- Blank coordinates previously became zero; they now stay blank and are rejected. Numeric bounds, finite values, integer/complete years and 60-year limit are validated. Backend rejects booleans and string coordinates rather than coercing them. Start-after-end produces a clear message.
- Frontend network failures previously exposed raw fetch errors, and non-JSON errors could hide useful feedback. A useful connection message, server error handling and timeout were added; loading exits through `finally`.
- Corrupted `1981?2010` and decorative punctuation repaired using UTF-8. Chart year initializes from the returned result range. CSV encoding moved to a tested serializer with RFC-style quote/comma/newline escaping and CRLF records.
- Results table header made sticky. Small-screen controls, long location labels and grid sizing constrained without redesigning the approved UI.

## Actual command results

| Command | Actual result |
| --- | --- |
| `.\.venv\Scripts\python.exe -m pytest Backend -q` | `27 passed, 1 warning in 1.03s` |
| `npm run typecheck` | `tsc -b`, exit 0 |
| `npx playwright test` | `9 passed (22.3s)`, installed Edge, headless |
| `python Backend/verify_live.py` using project venv | exit 0; real MongoDB/Open-Meteo results below |
| `npm run build` | Execution permission rejected; latest production build NOT verified |
| lint | No configured lint script or configuration |

The backend warning is an upstream Starlette/AnyIO deprecation warning, not a test failure. An earlier production build passed before these changes; that does not validate the current release. An intermediate browser test failed because its response years differed from its request; chart initialization was made result-consistent and the final suite passed. Earlier failures are not counted as passing checks.

## Real data and MongoDB caching

| Case | Years | Events | Days | Longest | Threshold | Coverage | First / second cached |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Delhi point 28.614, 77.209 | 1990?2021 | 73 | 432 | 21 | 41.5 ?C | 100% | false / true |
| Mumbai point 19.07283, 72.88261 | 1990?2021 | 88 | 380 | 13 | 33.4 ?C | 100% | false / true |
| Mumbai point | 2020?2021 | 7 | 32 | 7 | 33.4 ?C | 100% | false / true |

Repeated result contents matched except for the cached flag. Different coordinates and date ranges produced fresh distinct results. Baseline/model/source-parameter/algorithm invalidation and expiration were additionally tested with controlled in-memory collection fixtures; they were not exercised by changing the live provider/model. The fixed production baseline remains 1981?2010 and the model remains ERA5.

## CSV, filters, UI and recovery

- Actual Delhi and Mumbai 1990?2021 backend JSON captured in `verification/`. Browser download tests compared **every CSV field** with the backend annual summary through the tested serializer, confirmed 32 data rows, and summed event/day counts to the backend totals. Files: `verification/delhi-1990-2021.csv` and `verification/mumbai-1990-2021.csv`.
- Empty CSV emits its header only. Commas, double quotes and newlines are escaped in dedicated serializer tests. The current annual contract is numeric, so no location strings are exported.
- Browser tests confirmed Mumbai explicit selection, unchanged prior region before selection, selected coordinates, metric cards, threshold and event table. Ambiguous Bihar suggestions retain state/country/coordinates. Most UI scenarios use deterministic API fixtures; separate live checks exercise the actual backend/provider.
- Temperature year change altered the rendered SVG curve; daily filtering also tested directly. Invalid dates/coordinates, zero-event results, no matching places, upstream 502, non-JSON failure and network failure tested.
- At **390 ? 844**, both Home and populated Explorer passed document-width checks; controls remained within the viewport. Screenshots were generated and visually reviewed for Home and dashboard. These checks use Edge; no claim is made about all devices/browsers.
- A separate real uvicorn instance on **8011** was started, stopped and restarted by the browser suite. The browser showed the useful connection error, the Analyze button became enabled, and after restart the real Mumbai cached result (7 events) loaded. The user's existing backend on 8000 was not stopped.
- Diagnostic browser outputs/screenshots: `Frontend/test-results/` (git-ignored).

## Limitations and remaining release steps

- **Custom bounding-box selection and area averaging are NOT implemented.** Locations select one representative point/grid cell. State coverage must not be inferred. Geocoder data is not independently certified for every record; the verified records preserve provider identity.
- No rainfall/drought analysis, map picker, PDF export or statistical significance test. Those remain clearly labeled future features. Baseline/model are server constants, not user filters. Annual pooled percentile and range-clipped events retain the documented climate limitations.
- Rate limiting is process-local; raw historical weather cache does not automatically refresh for provider reanalysis revisions. Public hosting needs shared gateway controls, authenticated MongoDB, HTTPS and monitoring as documented.
- Latest production build remains unverified because permission was rejected. Run `cd Frontend; npm run build` in your terminal and resolve any errors before release. No lint setup exists.
- Deployment/GitHub tasks require your approval. Exact checklist and host commands are in README: review source/secrets, pass current checks, approve public repository creation/push, configure MongoDB/backend env, approve deployment, configure frontend API URL, verify live deployment, then submit URLs and README/AI disclosure. No assessment submission was sent.

## Subsequent sidebar update

Dedicated workspace routes added: `#/explorer`, `#/analyze`, `#/data`, `#/reports`, `#/about`. Analysis state is preserved while navigating between workspace pages; a full refresh or visiting Home resets this in-memory state. Data Explorer provides annual/event/daily tables, year filtering and 100-row daily pagination. Reports downloads annual CSV, event CSV and full JSON. Mobile sidebar includes open/close/backdrop controls and Escape dismissal.

`npm run typecheck` passed after the change. Two browser regression scenarios were added for navigation, state retention, report files and the mobile menu. Execution permission for the updated Playwright suite was rejected, so these changes have NOT been browser-verified. Earlier 9-test results apply to the prior version; no current production-build pass is claimed.

## HeatWave theme update

Home and workspace now use the supplied orange/red HeatWave reference style, sun branding, warm light header, dark sidebar with orange active state, and a project-local generated sunset city hero. Existing analysis and report functions retained. A four-step Watch Demo walkthrough is implemented; it is not a video. `npm run typecheck` passed. A browser scenario was added for the walkthrough, branding and desktop/mobile screenshots, but execution permission for Playwright was rejected; no current visual/browser pass is claimed. The theme update has not been production-built or deployed.
