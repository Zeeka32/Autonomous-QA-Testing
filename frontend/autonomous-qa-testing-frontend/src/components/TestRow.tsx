import type { TestCase, TestResult, TestStatus } from "../api/types";
import "./TestRow.css";

type DisplayStatus = TestStatus | "running" | "pending";

function StatusMark({ status }: { status: DisplayStatus }) {
  if (status === "running") {
    return <span className="status-mark status-mark--running" aria-hidden="true" />;
  }
  if (status === "pending") {
    return <span className="status-mark status-mark--pending" aria-hidden="true">·</span>;
  }
  const symbol = status === "passed" ? "✓" : status === "skipped" ? "–" : "×";
  return (
    <span className={`status-mark status-mark--${status}`} aria-hidden="true">
      {symbol}
    </span>
  );
}

type TestRowProps = {
  test: TestCase;
  result?: TestResult;
  running: boolean;
  active: boolean;
};

export function TestRow({ test, result, running, active }: TestRowProps) {
  const status: DisplayStatus = result?.status ?? (running ? "running" : "pending");
  const label = status === "pending" && !active ? "Not run" : status;

  return (
    <li className="test-row">
      <StatusMark status={status} />
      <div className="test-body">
        <div className="test-topline">
          <h4>{test.name}</h4>
          <span className={`test-status test-status--${status}`}>{label}</span>
        </div>
        <p className="test-kind">
          {test.kind.replaceAll("_", " ")}
          {result ? ` · ${(result.duration_ms / 1000).toFixed(1)}s` : ""}
        </p>
        {result && <p className="test-message">{result.message}</p>}
        {result && result.checks.length > 0 && (
          <details className="checks-detail">
            <summary>
              View {result.checks.length} check{result.checks.length === 1 ? "" : "s"}
            </summary>
            <ul>
              {result.checks.map((check, checkIndex) => (
                <li key={`${check.name}-${checkIndex}`}>
                  <span>{check.passed ? "✓" : "×"} {check.name}</span>
                  <span>{check.message}</span>
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </li>
  );
}
