# Deploy the assessment

No hosted resources are created by these files alone. Use your own accounts;
enter secrets only in the hosting dashboard. Never commit a real MongoDB URI.

## 1. MongoDB Atlas

Create an Atlas project and a free cluster if offered for your account/region.
Create a database user restricted to read/write on `climate_hazard`.
Copy its Drivers connection URI, substituting the database user's password
(URL-encode special characters). This is separate from your Atlas login.
Use Render's service outbound IP ranges in Atlas Network Access. Find those
ranges in the Render dashboard before completing the backend deployment.
Keep local unauthenticated MongoDB bound to localhost.

## 2. Reserve the frontend URL

In Vercel, import `ANMOL3568/climate-hazard-trend-analyzer`.
Choose root directory `Frontend`, framework Vite, build `npm run build`,
output `dist`. Record the assigned production URL. A first frontend deploy
can render the UI but analysis requires the backend URL in step 4.

## 3. Deploy FastAPI

In Render choose New > Blueprint and connect the same GitHub repository.
The root `render.yaml` defines the Python service on the free plan.
Enter the following values when prompted:

- `MONGODB_URI`: the authenticated Atlas URI, only in Render's secret settings.
- `CORS_ORIGINS`: the exact Vercel production origin, e.g.
  `https://your-project.vercel.app`, without a trailing slash or URL path.

Add Render's outbound IP ranges to Atlas, then deploy/restart the service.
Copy its assigned HTTPS URL. `/api/ready` must return HTTP 200 and
`{"status":"ready"}`; it checks the actual database connection.
An HTTP 503 means the database connection must be fixed before submission.
The runtime uses one worker to keep the public map-geocoder limiter serialized.
Free services may sleep; verify current provider limits and allow for cold starts.

## 4. Connect the frontend

In Vercel > Project Settings > Environment Variables, set `VITE_API_URL`
to the backend HTTPS origin (without a trailing slash), for Production.
Redeploy: Vite embeds this value at build time. Do not use localhost in production.
Add preview origins to backend CORS only if preview deployments need API access;
production configuration does not automatically permit arbitrary preview URLs.

## 5. Verify the live deployment

1. Open the live Home page, Dashboard and mobile layout at 390px.
2. Confirm `/api/ready` returns ready, and the browser has no CORS/mixed-content errors.
3. Select Delhi and Mumbai explicitly. Verify labels and coordinates agree.
4. Run the same selection twice; verify the response changes from fresh to cached.
5. Test map country/state search and point selection.
6. Test all three hazards, chart year filters, invalid years, API failure/recovery.
7. Export 1990-2021 annual CSV; confirm 32 rows and backend metric agreement.

Only after these checks submit the public GitHub URL and the Vercel production URL.
The latest local browser/build results do not verify this deployment.

If the first analysis times out on a sleeping free service, check backend logs and
retry after it is awake; never replace a failed request with dummy results.
