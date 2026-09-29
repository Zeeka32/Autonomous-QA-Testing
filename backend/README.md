# Autonomous QA Testing

## Project goal

Build a tool that accepts a website URL, opens the site in a real browser, runs
repeatable quality checks, and explains the results clearly.

## Version 0.1

The first version is a command-line application. A user provides one URL, the
application opens it in Chromium, runs deterministic checks, and prints a clear
pass-or-fail result for each check.

## Initial checks

- Navigation completes successfully.
- The main page response has an HTTP status below 400.
- The page title is not empty.

## Not included yet

The project does not yet include broad site crawling, authentication, a
database, an API, or a frontend. AI-driven runs are intentionally bounded to
the validated browser actions described below.

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

The JSON report contains an `actions` array with one record per attempted
browser action. Each record includes its step number, action kind, status
(`passed`, `failed`, or `skipped`), duration in milliseconds, URL before and
after, and a completion or failure message. After the first failed action,
later actions are recorded as skipped. The runner still captures the final page
state and writes the report when possible.

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
Plans are limited to 20 actions, and each browser action has a 10-second
timeout. The executor accepts only these action objects; it does not execute
arbitrary code or unvalidated commands.

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

OpenAI defaults to `gpt-5.6-luna`. Both providers can be given an explicit
model with `--model`.
