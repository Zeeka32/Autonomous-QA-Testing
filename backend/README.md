# Autonomous QA Testing

## Project goal

Build a tool that accepts a website URL, opens the site in a real browser, runs
repeatable quality checks, and explains the results clearly.

## Version 0.1

The first version is a command-line application. A user provides one URL, the
application opens it in Chromium, runs deterministic checks, and prints a clear
pass-or-fail result for each check.

## Version 0.2.0

Version 0.2.0 introduces validated multi-test suites. This release adds
immutable suite and result models, an executor-registry runner, concrete
executor adapters, a fixed deterministic suite, AI-generated suites from broad
requests, a bounded deterministic accessibility audit, suite budgets, a
reusable application service, and isolated output directories for each run.

See [CHANGELOG.md](CHANGELOG.md) for release highlights and compatibility notes.

## Code layout

`autonomous_qa` is the importable Python package, not an AI-specific project
convention. Its subpackages group related responsibilities:

- `browser/` owns Playwright execution, page observation, deterministic checks,
  assertions, accessibility checks, and browser-session runners.
- `suite/` defines test suites, runs their cases, connects test types to browser
  runners, and enforces execution budgets.
- The package root holds shared models and plans, AI planning and the agent
  loop, reporting, the application service, and the `cli.py` and `api.py`
  entry points. `run_jobs.py` supports background API requests.

The CLI and API both use `service.py`; neither contains the underlying QA
engine. Imports should use the new module paths, such as
`autonomous_qa.browser.runner` and `autonomous_qa.suite.suites`.

## Version 0.3.0

Version 0.3.0 adds a local HTTP API. It accepts runs immediately, executes them
in a small in-process worker pool, and lets clients poll results and download
reports, screenshots, and traces. CLI workflows are still available.

## Initial checks

- Navigation completes successfully.
- The main page response has an HTTP status below 400.
- The page title is not empty.

## Not included yet

The project does not yet include broad site crawling, authentication, or a
database. A small local frontend is available under `frontend/`.
AI-driven runs are intentionally bounded to the
validated browser actions described below.

## Running the HTTP API

From `backend/`, install the project dependencies if needed and start Uvicorn:

```bash
python -m pip install -e ".[dev]"
python -m uvicorn autonomous_qa.api:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/docs` to try the API interactively. Startup loads
`backend/.env` without overriding existing environment variables. API keys
stay on the server; clients supply only a provider/model choice.

Run the deterministic baseline suite without an AI request:

```bash
curl -X POST http://127.0.0.1:8000/runs \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com"}'
```

To generate a suite, add request text and optional budgets:

```json
{
  "url": "https://example.com",
  "request": "Test basic navigation",
  "provider": "gemini",
  "budget_policy": {"max_ai_requests": 6, "max_browser_runs": 3}
}
```

`POST /runs` returns immediately with HTTP `202`, a `run_id`, and a
`status_path`. The client calls `GET /runs/{run_id}` until `status` becomes
`completed` or `failed`. A completed response includes `passed`, `suite_run`
(suite definition and case results), `budget`, `report_path`, and
`artifact_directory`. `passed` can be false even when status is `completed`:
the run finished, but some tests failed or were skipped.

While a run is in progress, the same status endpoint also includes `suite`
once tests have been generated and `results` as an ordered list of completed
cases. Clients can poll these fields to show per-test progress. Before planning
finishes, `suite` is null and `results` is empty.

Output is stored under `qa-runs/<run-id>/` relative to the server working
directory. The response paths are server filesystem paths. Download files
through the API instead:

```text
GET /runs/{run_id}/report
GET /runs/{run_id}/artifacts
GET /runs/{run_id}/artifacts/{filename}
```

The artifact listing returns names and URLs for available screenshots and
traces. These endpoints read run files from disk, so they still work after an
API restart even though `GET /runs/{run_id}` no longer knows that run. Missing
files return `404`. Only a run's known screenshot and trace names are served;
arbitrary filenames and symlinks are rejected. Clients cannot choose output
paths. Python hosts can configure them through
`create_app(runs_directory=Path(...))`.

HTTP status codes:

- `202` from `POST /runs`: run accepted and queued.
- `200` from `GET /runs/{run_id}`: status is queued, running, completed, or
  failed. Inspect `passed` for a completed run.
- `422`: invalid input, such as a non-HTTP URL, blank request, or invalid budget.
- `404` from `GET /runs/{run_id}`: ID is unknown to this server process.
  Artifact endpoints return `404` when the run directory or file is missing.
- `429` from `POST /runs`: the in-process run queue is full.

Failed run statuses include a safe error code and message, budget usage when
available, and any completed suite results. The API distinguishes provider
quota/rate limits, unsupported test requests, missing or rejected credentials,
unavailable models, temporary provider outages, and exhausted run budgets.
For unsupported requests, the planner's short explanation is returned. Raw
provider exception details stay in server logs. A completed suite stopped by
a provider or run budget also includes a code and message alongside its skipped
test results. A busy provider can still cause a run to fail, but the original
`POST` no longer waits for that request to finish.

The in-memory registry allows two workers and eight active jobs (running plus
queued) by default. The ID and status are available only in the server process
that accepted the run; a restart loses status, though reports already written
to disk remain. Run the API with one Uvicorn worker for now. Graceful shutdown
waits for active runs. There is no persistent queue, cancellation, or
authentication yet. This milestone is intended for local use on loopback.

## Running the CLI

Run an inspection and write `qa-report.json`, `screenshot.png`, and `trace.zip`:

```bash
python -m autonomous_qa https://example.com
```

Choose a different report location with `--report`:

```bash
python -m autonomous_qa https://example.com --report reports/example.json
```

The screenshot and trace locations can also be changed:

```bash
python -m autonomous_qa https://example.com \
  --screenshot reports/example.png \
  --trace reports/example-trace.zip
```

The destination directories must already exist. Open a trace with:

```bash
playwright show-trace trace.zip
```

Run the fixed multi-test baseline suite:

```bash
python -m autonomous_qa https://example.com --suite
```

This runs independent page-load and title-presence test cases without calling
an AI provider. Each suite invocation gets a unique run ID and saves its report
and artifacts together:

```text
qa-runs/
  <run-id>/
    report.json
    artifacts/
      baseline-screenshot.png
      baseline-trace.zip
```

The CLI prints the run ID and output paths. Choose another parent directory
with `--runs-dir reports`; `--artifacts-dir` remains an alias for this option.
Both suite modes now create a new subdirectory on every invocation. The
`--report` option applies only to single-page, action-plan, and single-goal
modes; for suites, replace it with `--runs-dir`. Existing output is never
deleted or reused, even when the same request is run again.

Generate a suite from a broad request:

```bash
python -m autonomous_qa https://example.com \
  --request "Test the basic navigation"
```

The CLI first observes the initial page, then makes one structured AI request
to choose between one and five supported test cases. Generated cases are
validated as `page_load`, `title_present`, `accessibility`, or
`browser_goal` before they reach the suite runner. Browser-goal cases reuse
the existing bounded agent and may make additional requests for completion
criteria and individual actions. The initial page snapshot is reused by
deterministic page and title cases, so the page is not opened again for those
checks.

Every suite uses a shared execution budget. The defaults allow up to five
tests, two browser-goal cases, ten AI requests, five browser runs, and 120
seconds. Override them when needed:

```bash
python -m autonomous_qa https://example.com \
  --request "Test the basic navigation" \
  --max-suite-tests 4 \
  --max-browser-goals 1 \
  --max-ai-requests 6 \
  --max-browser-runs 3 \
  --max-suite-seconds 90
```

Limits are checked before each test and before starting an AI request or
browser run; they do not interrupt an operation already in progress. When a
limit is exhausted, the current and remaining cases are marked `skipped`.
Provider quota and rate-limit responses also stop the rest of the suite. The
JSON suite report records the configured limits, usage, elapsed time, and any
exhaustion reason.

For example:

```bash
python -m autonomous_qa https://example.com \
  --request "Test this page for accessibility"
```

The accessibility executor checks the document language and title, visible
image alt attributes, accessible names for visible form controls, buttons and
links, and titles for visible iframes. It records every check in the suite
report and writes a dedicated screenshot and trace. This is a bounded automated
audit, not a full WCAG conformance assessment.

The suite planner still cannot generate performance, security,
visual-regression, API, upload, download, authentication, or full/manual WCAG
audit tests because deterministic executors for those capabilities do not
exist. Goal and expectation flags cannot be combined with either suite mode.

The JSON report contains an `actions` array with one record per attempted
browser action. Each record includes its step number, action kind, status
(`passed`, `failed`, or `skipped`), duration in milliseconds, URL before and
after, and a completion or failure message. After the first failed action,
later actions are recorded as skipped. The runner still captures the final page
state and writes the report when possible.

## Calling the suite service from Python

Both `--suite` and `--request` delegate to `service.run_qa()`. The service
handles initial observation, suite generation, budgets, executors, and JSON
report writing. The CLI handles arguments, terminal output, and exit codes.
Single-page, action-plan, and single-goal modes retain their existing runners.

```python
from pathlib import Path
from autonomous_qa.service import QaRunRequest, run_qa

result = run_qa(QaRunRequest(
    url="https://example.com",
    runs_directory=Path("qa-runs"),
))
print(result.run_id)
print(result.report_path)
print(result.passed)
print(result.suite_run.results)
print(result.budget)
```

Omit `request` to run the deterministic baseline suite. Supply request text
such as `request="Test basic navigation"` to generate a suite using the selected
`provider` and `model`. Direct callers must configure provider credentials in
their environment; the service does not load `.env` or read command-line input.

`QaRunRequest` validates inputs before execution. `QaRunResult` contains the
run ID, run directory, suite, ordered case results, budget snapshot, and
report/artifact locations. The JSON report includes the same `run_id`.
Failed or skipped tests return normally with `passed=False`. Setup, planning,
and reporting failures raise `QaRunError`, which includes the run ID, output
paths, budget usage, and any completed suite results. A failed report write
does not discard those results. Planning failures may leave an artifact
directory without a report; the error paths indicate where to inspect it.

The service is silent by default. Optional `on_message` and `on_agent_step`
callbacks let callers receive planning diagnostics and agent progress. Direct
calls run synchronously; the HTTP API schedules those calls in its worker pool.
`run_storage.RunPaths` generates a UUID and reserves its directory before
execution. Directory creation is exclusive, so an ID collision fails instead
of overwriting an earlier run. There is no automatic cleanup yet.

## Running automated tests

Install the development dependencies with the editable project:

```bash
python -m pip install -e ".[dev]"
```

Then run the test suite:

```bash
python -m pytest -q
```

Most tests are browser-independent. The runner integration test starts a
temporary local HTTP server and uses the installed Playwright Chromium browser
to exercise a complete agent workflow without calling an AI provider.

## Deterministic action plans

Browser behavior is represented by a validated `ActionPlan`. The currently
allowed action types are navigation, clicking an element, filling an input,
waiting for an element to become visible, selecting a dropdown option, and
checking or unchecking native form controls, and pressing a limited set of
keys on an observed element.
Plans are limited to 20 actions. Navigation has a 40-second timeout; other
browser actions have a 10-second timeout. The executor accepts only these
action objects; it does not execute arbitrary code or unvalidated commands.

Run a JSON action plan instead of passing a URL directly:

```bash
python -m autonomous_qa --plan examples/example-plan.json
```

Example `plan.json`:

```json
{
  "actions": [
    { "kind": "navigate", "url": "https://example.com" },
    { "kind": "fill", "selector": "input[name='search']", "value": "QA" },
    { "kind": "select", "selector": "#country", "value": "eg" },
    { "kind": "check", "selector": "#terms" },
    { "kind": "uncheck", "selector": "#newsletter" },
    { "kind": "press", "selector": "input[name='search']", "key": "Enter" },
    { "kind": "click", "selector": "button[type='submit']" },
    { "kind": "wait_for", "selector": "main h1" }
  ],
  "assertions": [
    { "kind": "url_contains", "value": "/search" },
    { "kind": "title_contains", "value": "Search results" },
    { "kind": "element_visible", "selector": "main h1" },
    { "kind": "element_hidden", "selector": "#loading" },
    { "kind": "element_enabled", "selector": "#submit" },
    { "kind": "element_disabled", "selector": "#cancel" },
    { "kind": "element_checked", "selector": "#terms" },
    { "kind": "element_unchecked", "selector": "#newsletter" },
    {
      "kind": "element_value_equals",
      "selector": "#search",
      "value": "QA"
    },
    { "kind": "element_count_equals", "selector": ".result", "count": 3 },
    {
      "kind": "element_attribute_contains",
      "selector": "#status",
      "attribute": "class",
      "value": "complete"
    },
    {
      "kind": "element_text_contains",
      "selector": "main h1",
      "value": "Results"
    }
  ]
}
```

Provide either a URL or `--plan`, not both. JSON plans use a strict schema and
must begin with a navigation action. The optional `assertions` array supports
`url_contains`, `title_contains`, `element_visible`, `element_hidden`,
`element_enabled`, `element_disabled`, `element_checked`,
`element_unchecked`, `element_value_equals`, `element_count_equals`,
`element_attribute_contains`, and `element_text_contains`. Value equality is
exact; text and attribute matching are case-sensitive substring checks.
Assertions run after
every browser action has finished and contribute to the process exit code and
JSON report.

`check` supports native checkbox and radio inputs. `uncheck` supports native
checkbox inputs only; radio buttons are changed by checking a different radio
option.

`press` supports only `Enter`, `Escape`, `Tab`, `ArrowUp`, and `ArrowDown`.
Key combinations and arbitrary text entry are deliberately excluded; use
`fill` for text.

## Page observation

After executing a plan, the runner records a bounded description of up to 100
visible interactive elements in the JSON report. Each record contains a CSS
selector hint, element tag, role, short label, input type, disabled state, and
link target. Select elements also include up to 50 enabled option values, each
limited to 160 characters. Native checkbox and radio observations include
their current checked state. It does not collect page HTML, scripts, cookies,
browser storage, or current text-input values.

## AI planning

Create a local credential file before using AI planning:

```bash
cp .env.example .env
```

Then place your Gemini API key in `.env`:

```dotenv
GEMINI_API_KEY=your_api_key_here
```

The real `.env` file is ignored by Git. Environment variables supplied by the
shell or deployment platform take priority over values in the file.

Pass a natural-language goal to use the default Gemini planner:

```bash
python -m autonomous_qa https://example.com \
  --goal "Open the Learn more link"
```

When no expectation flags are supplied, the model receives the initial page
observation in a separate one-time request and proposes deterministic
completion criteria. The application validates and freezes those criteria
before the action loop begins. Explicit criteria always take priority and skip
this generation request.

Completion criteria can check the final URL, title, element visibility,
enabled/disabled state, checked/unchecked state, exact form-control value,
element count, attribute content, or rendered element text:

```bash
python -m autonomous_qa https://example.com \
  --goal "Submit the form" \
  --expect-title-contains "Complete" \
  --expect-element-visible "#result" \
  --expect-element-hidden "#loading" \
  --expect-element-disabled "#submit" \
  --expect-element-checked "#terms" \
  --expect-element-value "#name" "Ada" \
  --expect-element-count ".result" 3 \
  --expect-element-attribute "#status" "class" "complete" \
  --expect-element-text "#result" "Submission complete"
```

These checks use case-sensitive matching. They are included in the terminal
output and JSON report with the generic checks. Generated URL criteria must be
grounded in an observed link target, and generated element selectors must come
from the initial observation. If the model cannot propose safe criteria, or if
its criteria were already true before any action, the run becomes `unverified`
and exits with failure status.

The CLI opens the page once and runs a bounded agent loop. On each step it
observes the current page, asks the configured AI model for one structured
decision, validates that decision, and executes the action deterministically.
The browser is observed again after every action, so the model works from the
latest page state. The loop stops when the model reports completion, reports
that it is blocked, the recovery budget is exhausted, or the ten-action safety
limit is reached. The final status and every decision are saved under `agent`
in the JSON report.

The report records the frozen criteria, their reason, and whether their source
was `user_provided` or `ai_generated`. The same frozen completion criteria are
included in every planning request, so the model can use them while choosing
its next action but cannot modify them. When the model reports
completion, the agent evaluates the deterministic
criteria immediately. It accepts completion only when every check passes. A
failed verification is sent back to the planner with a fresh observation so
it can continue working. Two verification retries are allowed; another failed
completion claim produces `verification_failed`. Each attempt and its evidence
are recorded in `agent.steps`, and `agent.verification_retries_used` records
the consumed retry budget.

An action failure is recoverable within a budget of two retries. The next
planning request receives the failed action's kind, selector, URLs, and error
message together with a fresh page observation. This lets the model choose a
different observed control instead of blindly repeating the same action. A
third failed action ends the run. Recovered failures remain visible in the
`actions` and `agent.steps` report records, while `agent.recoveries_used`
records how much of the budget was consumed. A recovered run passes only when
the agent eventually reports completion and all final checks pass. Initial
navigation failure is never retried.

Choose a provider and model with `--provider` and `--model`. Gemini is the
default provider and uses `gemini-3.8-flash`; its key is read from
`GEMINI_API_KEY`.

OpenAI remains available by placing `OPENAI_API_KEY` in `.env` and running:

```bash
python -m autonomous_qa https://example.com \
  --goal "Open the Learn more link" \
  --expect-url-contains "iana.org" \
  --provider openai
```

OpenAI defaults to `gpt-5.6-luna`. Cohere is also available by placing
`COHERE_API_KEY` in `.env` and selecting `--provider cohere` (or `"provider":
"cohere"` in an API run). Its default model is `command-a-03-2025`.
Any provider can be given an explicit model with `--model`.
