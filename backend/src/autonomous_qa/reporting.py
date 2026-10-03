import json
from dataclasses import asdict
from pathlib import Path

from .agent import AgentRunResult, AgentStatus
from .suite.budgets import SuiteBudgetSnapshot
from .models import CheckResult, PageSnapshot
from .plans import CompletionCriteria
from .suite.suites import SuiteRunResult


class ReportWriteError(RuntimeError):
    """Raised when a QA report cannot be written."""


def write_json_report(
    path: Path,
    requested_url: str,
    snapshot: PageSnapshot,
    results: list[CheckResult],
    screenshot_path: Path,
    trace_path: Path,
    agent_run: AgentRunResult | None = None,
    completion_criteria: CompletionCriteria | None = None,
) -> None:
    actions_passed = (
        all(action.status == "passed" for action in snapshot.action_results)
        if agent_run is None
        else agent_run.status is AgentStatus.COMPLETE
    )
    report = {
        "requested_url": requested_url,
        "final_url": snapshot.url,
        "status": snapshot.status,
        "title": snapshot.title,
        "observation": (
            asdict(snapshot.observation)
            if snapshot.observation is not None
            else None
        ),
        "passed": (
            actions_passed
            and all(result.passed for result in results)
        ),
        "actions": [asdict(action) for action in snapshot.action_results],
        "completion": (
            {
                "source": str(completion_criteria.source),
                "reason": completion_criteria.reason,
                "criteria": [
                    asdict(assertion)
                    for assertion in completion_criteria.assertions
                ],
            }
            if completion_criteria is not None
            else None
        ),
        "agent": (
            {
                "status": str(agent_run.status),
                "reason": agent_run.reason,
                "recoveries_used": agent_run.recoveries_used,
                "verification_retries_used": (
                    agent_run.verification_retries_used
                ),
                "steps": [asdict(step) for step in agent_run.steps],
            }
            if agent_run is not None
            else None
        ),
        "checks": [asdict(result) for result in results],
        "artifacts": {
            "screenshot": str(screenshot_path),
            "trace": str(trace_path),
        },
    }

    try:
        path.write_text(
            json.dumps(report, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as error:
        raise ReportWriteError(
            f'Could not write report to "{path}": {error}'
        ) from error


def write_suite_json_report(
    path: Path,
    suite_run: SuiteRunResult,
    artifact_directory: Path,
    budget_snapshot: SuiteBudgetSnapshot | None = None,
    run_id: str | None = None,
) -> None:
    tests = []
    for test, result in zip(
        suite_run.suite.tests,
        suite_run.results,
        strict=True,
    ):
        tests.append(
            {
                "test_id": test.test_id,
                "name": test.name,
                "kind": str(test.kind),
                "goal": test.goal,
                "status": str(result.status),
                "duration_ms": result.duration_ms,
                "message": result.message,
                "checks": [asdict(check) for check in result.checks],
            }
        )

    report = {
        "requested_url": suite_run.suite.url,
        "request": suite_run.suite.request,
        "passed": suite_run.passed,
        "tests": tests,
        "artifacts": {
            "directory": str(artifact_directory),
        },
    }
    if run_id is not None:
        report["run_id"] = run_id
    if budget_snapshot is not None:
        report["budget"] = {
            "limits": asdict(budget_snapshot.policy),
            "usage": {
                "ai_requests": budget_snapshot.ai_requests_used,
                "browser_runs": budget_snapshot.browser_runs_used,
                "elapsed_seconds": budget_snapshot.elapsed_seconds,
            },
            "exhausted": budget_snapshot.exhausted,
            "reason": budget_snapshot.exhausted_reason,
        }

    try:
        path.write_text(
            json.dumps(report, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as error:
        raise ReportWriteError(
            f'Could not write report to "{path}": {error}'
        ) from error
