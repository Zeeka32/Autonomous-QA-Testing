import { apiPath } from "../api/qa";
import type { Artifact, Run, Suite, TestResult } from "../api/types";
import { TestRow } from "./TestRow";
import "./RunOverview.css";

type RunOverviewProps = {
  runId: string | null;
  run: Run | null;
  artifacts: Artifact[];
  error: string | null;
  active: boolean;
};

function runLabel(runId: string, run: Run | null, suite: Suite | null): string {
  if (run?.status === "queued") return "Waiting for a worker";
  if (run?.status === "running") {
    return suite ? "Running tests" : "Inspecting site and planning tests";
  }
  if (run?.status === "completed") {
    return run.passed ? "All tests passed" : "Run completed with issues";
  }
  if (run?.status === "failed") {
    if (run.code === "provider_quota") return "AI quota or rate limit reached";
    if (run.code === "unsupported_request") return "Request not supported";
    if (run.code === "budget_exhausted") return "Run budget exhausted";
    return "Run stopped early";
  }
  return runId ? "Starting run" : "Ready for a new run";
}

export function RunOverview({
  runId,
  run,
  artifacts,
  error,
  active,
}: RunOverviewProps) {
  const suite = run?.suite ?? run?.suite_run?.suite ?? null;
  const results: TestResult[] = run?.results ?? run?.suite_run?.results ?? [];
  const resultById = new Map(results.map((result) => [result.test_id, result]));
  const total = suite?.tests.length ?? 0;
  const passed = results.filter((result) => result.status === "passed").length;
  const failed = results.filter(
    (result) => result.status === "failed" || result.status === "error",
  ).length;

  return (
    <section className="panel results-panel" aria-labelledby="results-heading">
      <div className="panel-heading">
        <div>
          <p className="section-kicker">02 / RESULTS</p>
          <h2 id="results-heading">Run overview</h2>
        </div>
        <span className={`run-state ${active ? "run-state--active" : ""}`}>
          <span className="run-state-dot" />
          {run?.status ?? "idle"}
        </span>
      </div>

      {error && <div className="notice notice--error" role="alert">{error}</div>}

      {!runId ? (
        <div className="empty-state">
          <div className="empty-illustration" aria-hidden="true">
            <span>01</span><span>02</span><span>03</span>
          </div>
          <h3>Your results will appear here</h3>
          <p>Start a run to see the generated tests and watch their results come in.</p>
        </div>
      ) : (
        <div className="run-content" aria-live="polite">
          <div className="run-summary">
            <div>
              <p className="summary-label">CURRENT STATUS</p>
              <h3>{runLabel(runId, run, suite)}</h3>
              <p className="run-id">Run {runId.slice(0, 12)}</p>
            </div>
            <div className="summary-count">
              {results.length}<span>/{total || "—"}</span>
            </div>
          </div>
          <div
            className={`progress-track ${active && !suite ? "progress-track--indeterminate" : ""}`}
            role="progressbar"
            aria-label="Tests completed"
            aria-valuemin={0}
            aria-valuemax={total || 1}
            aria-valuenow={results.length}
          >
            <span style={{ width: total ? `${(results.length / total) * 100}%` : "0%" }} />
          </div>

          {suite ? (
            <>
              <div className="metrics">
                <div><strong>{total}</strong><span>Tests</span></div>
                <div><strong className="metric-pass">{passed}</strong><span>Passed</span></div>
                <div><strong className="metric-fail">{failed}</strong><span>Issues</span></div>
              </div>
              <div className="test-list-header">
                <h3>Test cases</h3>
                <span>{results.length} of {total} complete</span>
              </div>
              <ol className="test-list">
                {suite.tests.map((test, index) => (
                  <TestRow
                    key={test.test_id}
                    test={test}
                    result={resultById.get(test.test_id)}
                    running={active && index === results.length && run?.status === "running"}
                    active={active}
                  />
                ))}
              </ol>
            </>
          ) : active || !run ? (
            <div className="planning-state">
              <span className="planning-spinner" aria-hidden="true" />
              <p>
                {run?.status === "queued"
                  ? "Your run is in the queue."
                  : "The test list will appear after planning finishes."}
              </p>
            </div>
          ) : run.status === "failed" ? (
            <div className="failure-state" role="alert">
              <span className="failure-mark" aria-hidden="true">×</span>
              <div>
                <h4>No test suite was generated</h4>
                <p>{run.message ?? "The run stopped before tests could begin."}</p>
              </div>
            </div>
          ) : (
            <div className="failure-state">
              <p>No test suite is available for this run.</p>
            </div>
          )}

          {run?.status === "failed" && suite && (
            <div className="notice notice--error" role="alert">
              {run.message ?? "The run could not finish."}
            </div>
          )}

          {run?.status === "completed" && run.message && (
            <div className="notice notice--error" role="alert">
              {run.message}
            </div>
          )}

          {run?.status === "completed" && (
            <div className="downloads">
              <h3>Run files</h3>
              <div className="download-links">
                <a href={apiPath(`/runs/${runId}/report`)} target="_blank" rel="noreferrer">
                  JSON report ↗
                </a>
                {artifacts.map((artifact) => (
                  <a
                    key={artifact.path}
                    href={apiPath(artifact.path)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {artifact.name} ↗
                  </a>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
