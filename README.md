# Autonomous QA Testing

A local web-app QA demo. Give it a URL and, optionally, a plain-language test
request. A Python backend opens the site in Playwright's Chromium browser,
runs a bounded set of checks, and exposes results through a FastAPI service.
The React frontend shows generated tests and their results as each case
finishes. The backend also has a command-line interface.

## What it can test

With no request, it runs deterministic page-load and title checks without AI.
With a request, Gemini, OpenAI, or Cohere can propose a suite of these
supported test types:

- **Page load:** the main response has an HTTP status below 400.
- **Title present:** the page title is not empty.
- **Basic accessibility:** bounded checks for document language and title,
  image alt attributes, accessible names, and iframe titles.
- **Browser goal:** a specific workflow using observed links, buttons, form
  controls, and supported keyboard actions. The AI chooses validated actions;
  Playwright executes them and deterministic checks decide whether the goal
  passed.

Runs have limits on test count, AI requests, browser sessions, and elapsed
time. The UI polls for per-test progress; it does **not** show the browser
page live. Completed runs can provide a JSON report, screenshots, and
Playwright traces.

## Current limitations

This is not an arbitrary website-testing agent. It does not crawl a whole
site, log in, or run performance, security, visual-regression, API,
upload/download, or full WCAG audits. AI requests can also fail because of
provider availability, rate limits, or quota.

The agent freezes its pass conditions before acting. It can follow an observed
link, but it cannot yet discover controls on a *different* page and then
create new pass conditions for them. For example, starting at a homepage and
asking it to open a Checkboxes link and test the checkboxes may stop before
clicking; start at the checkbox page instead. Multi-page discovery is a known
next step.

This is intended for local use, not public deployment: the API has no user
authentication, cancellation, database, or persistent job queue. Run status
is lost when the server restarts, although saved files remain. If a run fails
before a suite finishes, it may leave a trace without a JSON report.

## Run locally

Start the API from the `backend/` directory:

```bash
cd backend
python -m pip install -e ".[dev]"
python -m playwright install chromium
python -m uvicorn autonomous_qa.api:app --host 127.0.0.1 --port 8000
```

In a second terminal, start the UI:

```bash
cd frontend/autonomous-qa-testing-frontend
npm install
npm run dev
```

Open the URL printed by Vite (normally `http://localhost:5173`). Leave the
request blank to try the deterministic checks. For AI-generated suites,
configure the selected provider's key in `backend/.env`; see the
[backend setup guide](backend/README.md#ai-planning). No key is needed for a
blank request.

## Project layout

- [`backend/`](backend/README.md) contains the Python CLI, FastAPI service,
  Playwright execution, AI planning, and tests. Its README covers API and CLI
  usage, configuration, and backend internals.
- [`frontend/autonomous-qa-testing-frontend/`](frontend/autonomous-qa-testing-frontend/README.md)
  contains the React UI and frontend setup notes.
