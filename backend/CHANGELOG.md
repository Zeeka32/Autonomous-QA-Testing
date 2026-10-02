# Changelog

## 0.2.0 — 2026-10-02

### Added

- Validated suite and result models, a suite runner, and executor adapters.
- Fixed baseline suites through `--suite` and AI-generated suites through
  `--request`, using the existing OpenAI-compatible and Gemini planner paths.
- Deterministic checks for page load, title presence, and basic accessibility,
  alongside bounded AI browser-goal execution.
- Shared suite budgets for test count, browser goals, AI requests, browser
  runs, and elapsed time. Budget exhaustion skips remaining work, and provider
  quota/rate-limit errors stop suite execution.
- A reusable `run_qa()` service with validated requests, structured results,
  optional progress callbacks, and errors that preserve completed results.
- Unique run IDs and isolated report, screenshot, and trace directories.
- Automated coverage for suite planning, execution, budgets, service errors,
  output isolation, and real-browser workflows.

### Compatibility notes

- Suite outputs now live under `qa-runs/<run-id>/`, containing `report.json`
  and an `artifacts/` directory.
- Use `--runs-dir` to choose the parent output directory for suites.
  `--artifacts-dir` is an alias; both create a new subdirectory per run.
- `--report` remains available for single-page, action-plan, and single-goal
  modes, but cannot be combined with suite modes.
- Service callers provide `QaRunRequest.runs_directory` and obtain actual
  report/artifact paths from the returned result or execution error.

### Limitations

- Accessibility checks are a bounded automated audit, not full WCAG coverage.
- Time budgets are checked between operations and do not interrupt an active
  browser operation or provider request.
- Execution is synchronous. No HTTP API, background jobs, database, automatic
  artifact cleanup, authentication, or broad site crawling is included.
- Suite generation supports only the implemented test kinds; it does not
  provide general security, performance, or visual-regression testing.
