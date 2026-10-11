# Clime — Climate Hazard Trend Analyzer

React/TypeScript dashboard and Python/FastAPI API for historical heatwave analysis. No sample temperatures or simulated analysis are presented as real observations.

## Run locally (Windows PowerShell)

1. Create the environment and install backend packages:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r Backend/requirements.txt
   Copy-Item Backend/.env.example Backend/.env
   ```

2. Start MongoDB locally, or put an Atlas connection URI in `Backend/.env`. If Docker is installed, run `docker compose up -d` from the project root. The compose database is bound to loopback only. Do not expose an unauthenticated database publicly.

3. Start the API:

   ```powershell
   cd Backend
   ..\.venv\Scripts\python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
   ```

4. In a second terminal:

   ```powershell
   cd Frontend
   npm ci
   npm run dev
   ```

5. Open http://localhost:5173. Search a city/state, select a result (or enter coordinates), select complete years and run analysis. `/api/health` reports database availability; `/docs` documents the API. Restart the API after changing database configuration or restoring a database that was unavailable at startup.

## Architecture

Browser → FastAPI validation/rate limit → MongoDB analysis cache → cached or fetched daily ERA5 temperatures → cleaning → fixed-baseline percentile → event detection → annual statistics and JSON → charts/export.

MongoDB `weather` stores source daily records by complete source settings, rounded point and year range. Analysis keys additionally include baseline and algorithm version. Expiration is checked on reads rather than relying on delayed TTL cleanup. Old key formats are intentionally bypassed. `cache` stores analysis results with a 30-day TTL. Only the backend connects to MongoDB. First uncached queries fetch baseline and requested years; subsequent results come from the database. No memory-only substitute hides database failures.

## Climate assumptions

- Source: [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api), ERA5, daily maximum temperature in Celsius, local timezone (`auto`). ERA5 is reanalysis, not a direct measurement at a city weather station. Retaining a single model avoids changes caused by mixing models over decades.
- Baseline: 1981–2010, all daily maximum values pooled into a single regional 95th percentile, linearly interpolated between observations. At least 95% baseline coverage is required. This simplified assessment definition is not a seasonal climatology or an official health alert criterion.
- Heatwave: at least three consecutive calendar days **strictly greater** than the unrounded threshold. Missing/non-finite/implausible temperatures (outside −90 to 65 °C) break runs. Valid hot extremes are retained. No interpolation of missing observations.
- Coordinates round to three decimal places consistently for requests and cache keys. City/state geocoding selects a representative point, not an area average. Custom coordinates are supported; a bounding-box area average is not implemented.
- Whole calendar years only, from 1940 to the previous year, maximum 60 years per query. Events are clipped at range boundaries and may therefore be omitted/truncated there. Cross-year events count in their start year, while their days contribute to each respective calendar year.
- Annual event frequency, days and coverage are returned. Five-year trailing average uses the available years at the start. Ordinary least-squares slope describes days/year, suppressed with less than 95% overall coverage or a single year. It is not a significance test or causal attribution; missing data can bias counts even above this cutoff. A threshold displayed with rounding is only a presentation value.

## Safety and operational limits

Environment variables hold credentials; `.env` is ignored. Explicit CORS origins, bounded numeric input, fixed upstream URLs, upstream timeouts, a three-analysis semaphore and a 30-request/minute per-client limit protect the local service. The limiter is process-local and does not trust forwarded headers. For public deployment, use a gateway with shared rate limiting, trusted proxy configuration, HTTPS, database authentication/network restrictions and monitoring. This is an assessment app, not an emergency warning system.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest Backend -q
cd Frontend
npm run typecheck
npm run test:e2e
npm run build
```

Backend regression tests cover climate rules, full geocoding identity, invalid coordinates, input validation, cache key configuration and expiration. Playwright uses installed Microsoft Edge to test selection, chart-year updates, downloaded CSV, API errors/recovery and 390px layout. Its separate stop/restart backend uses port 8011; it does not stop your backend on port 8000. That test requires MongoDB and the live verification cache. On other platforms, configure the browser channel and Python executable in the test configuration.

Before live-data CSV and backend recovery tests, seed reviewable evidence from the project root:

```powershell
.\.venv\Scripts\python.exe Backend/verify_live.py
```

This calls the real geocoder/weather service and writes public weather evidence to `verification/`. Live checks require MongoDB and internet. `test:e2e` can reuse your running Vite server. No lint script/configuration exists; `typecheck` is the configured static check. See [VERIFICATION.md](VERIFICATION.md) for actual results and limits.

## Deployment

Frontend: deploy `Frontend` to Vercel, build `npm run build`, output `dist`; set `VITE_API_URL` to the HTTPS backend URL before building. Backend: deploy `Backend` to a Python web host with install command `pip install -r requirements.txt` and start command `uvicorn main:app --host 0.0.0.0 --port $PORT`. Set `MONGODB_URI` and `CORS_ORIGINS` to the actual frontend origin. Free-host availability/limits must be checked when choosing a provider. No deployment has been created by this repository alone.

## Submission and future work

Submit your public repository URL and verified deployed app URL. Keep the assessment brief and screenshots out of the repository. Optional: record a 3–5 minute walkthrough of inputs, interpretation, caching, assumptions and failure states.

With more time: area-weighted bounding-box analysis, day-of-year percentile thresholds, sensitivity analysis, confidence intervals/Mann–Kendall, additional browser coverage and PDF export. Yearly CSV export is implemented.

## AI usage

OpenAI Codex assisted with architecture, code, styling, tests and documentation. The developer should review the calculations and be prepared to explain implementation decisions during the interview. Verification results and remaining setup requirements should accompany submission.

## Location identity and analysis scope

Geocoding uses [Open-Meteo/GeoNames](https://open-meteo.com/en/docs/geocoding-api). Suggestions preserve each record's ID, name, state, country and coordinates together; selection is explicit. Comma qualifiers are passed through to the geocoder. Invalid coordinate records are discarded. This validates record structure and preserves provider identity; it is not an independent survey of every place.

The suspicious 27.29201, 79.32543 result is GeoNames ID 10470188: Bih?r, Uttar Pradesh, India, a populated place, not Bihar state. Similar names also exist in Bangladesh and Pakistan. The selected label and all suggestions now show state/country and suggestion coordinates. To study a point within Bihar state, search Patna and select the India/Bihar result. A place-name match does not mean statewide analysis. Geographic labels use provider data; no state boundaries or area averaging are implemented.

## Approval-gated submission checklist

1. Restart the backend to load fixes (`cd Backend`, `python run.py`), then refresh the frontend.
2. Run the current backend tests, `npm run typecheck`, `npm run test:e2e` and `npm run build`. Resolve failures before packaging. The latest build was not authorized during the verification session; the old dist folder must not be treated as the latest release.
3. Review tracked files; exclude `.env`, `.venv`, `node_modules`, credentials, local runtime data and the private assessment brief.
4. With your explicit approval, create a public GitHub repository, initialize Git here if needed, commit the reviewed source/lockfiles/docs/tests and push it. No remote or repository has been created by this task.
5. Configure an authenticated hosted MongoDB and backend host with `MONGODB_URI`, frontend `CORS_ORIGINS`, requirements install and uvicorn start command documented above.
6. With your deployment approval, deploy the Python service and frontend; set `VITE_API_URL` before the frontend build.
7. Verify the HTTPS deployment: DB health, Delhi/Mumbai selection, fresh/cache requests, 32-row CSV, chart-year changes, invalid inputs and mobile layout. Check browser console and network for CORS errors.
8. Submit the public repository URL, live app URL and README/AI-use disclosure through the assessment form. Optional: a 3?5 minute walkthrough.


## Map-based point selection

On Dashboard or Analyze, click **Select on map**. Click a point to update the selected latitude/longitude, then click **Run analysis**. Drag to pan; use + / - to zoom and Recenter to return to the selected point. Keyboard: arrow keys pan and Enter selects the center. Choosing a search result also recenters the open map.

The map uses OpenStreetMap tiles with visible attribution, without additional npm dependencies. Tile loading needs an internet connection; if it fails, location search and manual coordinates remain available. A map selection is labeled Map-selected point rather than inheriting a previous city name. This selects one ERA5 grid cell, not a bounding box or statewide average. Web Mercator display is limited to approximately +/-85.05 degrees latitude.

Map verification: TypeScript check passed after implementation. Three regression tests cover projection, point selection/search/API synchronization/mobile width, and tile failure. Their browser execution was not authorized in this session, so they remain unverified. Run `cd Frontend` then `npm run test:e2e -- --grep "map "` and `npm run build` before release. Earlier successful build and 12-test results predate this feature.


### Country and state map picker

Open **Select on map**, search with **Country** selected, and explicitly choose a result. The picker switches to **State / province** and restricts subsequent state searches to that country's ISO code. Select the state result to zoom to its returned map extent and select its reference point. Use **World view**, zoom, dragging, or a map click to refine the point. Country/state reference points still feed the existing single-cell weather pipeline; map extents are for navigation, not spatial averaging or boundary selection.

Administrative search uses OpenStreetMap Nominatim through `/api/map-regions`, separately from the existing Open-Meteo city search. Requests are explicit (no autocomplete), serialized at least 1.1 seconds apart per backend process, and cached for 24 hours (maximum 256 queries). `MAP_GEOCODER_URL` can replace the default search endpoint. For deployment with multiple workers/replicas or higher usage, configure a suitable provider/shared rate limiter instead of multiplying requests to the public Nominatim service. Attribution remains visible on the map. Search requires internet access and can return ambiguous matches or no results; choose a result explicitly. No reverse geocoding is claimed for arbitrary map clicks.

Latest country/state picker verification: backend `python -m pytest Backend -q`: **29 passed**, one dependency deprecation warning. Frontend `npm run typecheck`: passed. Production build was blocked by sandbox `spawn EPERM`; its elevated retry was declined. Browser tests were added but not executed successfully in this session. Run `npx playwright test --grep map` from Frontend (or the full `npm run test:e2e`) and `npm run build` locally before submission.


## Additional hazards

Hazard type now accepts `heatwave` (default), `heavy_rainfall`, and `drought`. Precipitation comes from Open-Meteo ERA5 daily `precipitation_sum` in mm (rain plus snow water equivalent). Heavy Rainfall groups 1+ consecutive days strictly above the 95th percentile of wet days (>=1 mm/day) in 1981-2010. Baseline coverage must be >=95%; no wet baseline days returns a validation error instead of an invented threshold. This is a precipitation-extreme indicator rather than a flood prediction.

Drought is explicitly a **dry-spell proxy**, defined here as 15+ consecutive days with precipitation <1 mm/day. The 15-day cutoff is an application assumption, not a universal drought standard. It does not calculate SPI/SPEI, soil-moisture deficits, agricultural impacts, or seasonally adjusted drought severity. No percentile baseline is used for this fixed cutoff. Missing/invalid precipitation breaks events. Precipitation cannot be negative; finite nonnegative values (including values >65 mm) remain valid. Date-range boundary clipping and single-grid-cell limitations apply to all hazards.

Both hazards use the existing annual event/day metrics, rolling averages, coverage and trend suppression, with precipitation charts/event values in mm and hazard-specific CSV headers/filenames. Cache identities include hazard and algorithm version; precipitation raw data has a distinct weather-cache key. Old heatwave requests remain compatible when hazard is omitted. A hazard change clears the displayed result before the next run.

Verification after this change: 32 backend tests passed (one dependency deprecation warning); TypeScript check passed. New browser regression coverage is added for dropdown payloads, precipitation units, state reset and hazard CSV downloads, but browser execution and live precipitation-provider checks remain pending. Run the full frontend suite and production build before release.


## Hosting setup

See [DEPLOYMENT.md](DEPLOYMENT.md) for Render + Vercel + MongoDB Atlas deployment. The repository includes a Render Blueprint and Vercel build configuration. Hosting readiness uses `/api/ready` (HTTP 503 when MongoDB is unavailable). These files do not mean a live deployment exists.
