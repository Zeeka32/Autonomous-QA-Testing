# Autonomous QA frontend

A small React + Vite interface for the local QA API. Enter a website URL and
an optional test request, start a run, and watch the generated cases receive
results as they finish. A blank request runs the deterministic baseline checks.

## Run locally

Start the backend from `backend/`:

```bash
python -m uvicorn autonomous_qa.api:app --host 127.0.0.1 --port 8000
```

Start this frontend from `frontend/autonomous-qa-testing-frontend/`:

```bash
npm install
npm run dev
```

Open the URL printed by Vite (normally `http://localhost:5173`). The Vite dev
server forwards `/api/*` requests to the backend on port 8000. API credentials
stay in the backend environment and are never sent to the browser.

The UI polls `GET /runs/{id}` approximately every 1.2 seconds. During a run,
the endpoint returns the generated `suite` and an ordered `results` list that
grows as tests finish. This is test progress, not a live view of the website.
Progress is held in the backend process, so a server restart loses active run
status. For a production build, configure a reverse proxy for `/api/*`.

If planning fails before a suite is generated, the results panel shows the
terminal error instead of a planning spinner. The API supplies safe, specific
messages for provider quota, unsupported requests, and other common provider
failures; raw provider responses remain in server logs.

## Code layout

- `src/api/` contains the API response types and HTTP requests.
- `src/hooks/useQaRun.ts` owns submission, polling, and artifact loading state.
- `src/components/` contains the form, overview, test row, header, and intro.
  Each component has a nearby CSS file for its own styles.
- `src/App.tsx` only composes the screen; `src/App.css` holds shared layout,
  while `src/index.css` holds global defaults.
