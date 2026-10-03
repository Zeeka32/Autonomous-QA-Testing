import json

import pytest

from autonomous_qa.suite.budgets import (
    SuiteBudgetTracker,
    SuiteExecutionPolicy,
)
from autonomous_qa.agent import (
    AgentRunResult,
    AgentStatus,
    AgentStepResult,
)
from autonomous_qa.models import (
    ActionResult,
    CheckResult,
    InteractiveElement,
    PageObservation,
    PageSnapshot,
)
from autonomous_qa.planner import DecisionStatus
from autonomous_qa.reporting import (
    ReportWriteError,
    write_json_report,
    write_suite_json_report,
)
from autonomous_qa.suite.suites import (
    SuiteRunResult,
    TestCase as SuiteCase,
    TestCaseResult as SuiteCaseResult,
    TestKind as SuiteTestKind,
    TestStatus as CaseStatus,
    TestSuite as SuiteDefinition,
)


def test_write_json_report_saves_results_and_artifact_paths(tmp_path) -> None:
    report_path = tmp_path / "report.json"
    screenshot_path = tmp_path / "page.png"
    trace_path = tmp_path / "trace.zip"
    snapshot = PageSnapshot(
        url="https://example.com/",
        status=200,
        title="Example Domain",
        observation=PageObservation(
            elements=(
                InteractiveElement(
                    selector="#submit",
                    tag="button",
                    role="button",
                    label="Submit",
                    input_type=None,
                    disabled=False,
                    href=None,
                ),
            ),
            truncated=False,
        ),
        action_results=(
            ActionResult(
                step_number=1,
                kind="navigate",
                status="passed",
                duration_ms=12.5,
                url_before="about:blank",
                url_after="https://example.com/",
                message='Navigated to "https://example.com"',
            ),
        ),
    )
    results = [
        CheckResult(
            name="HTTP status",
            passed=True,
            message="Page returned HTTP 200",
        )
    ]

    write_json_report(
        report_path,
        "https://example.com",
        snapshot,
        results,
        screenshot_path,
        trace_path,
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["requested_url"] == "https://example.com"
    assert report["final_url"] == "https://example.com/"
    assert report["passed"] is True
    assert report["agent"] is None
    assert report["completion"] is None
    assert report["actions"] == [
        {
            "step_number": 1,
            "kind": "navigate",
            "status": "passed",
            "duration_ms": 12.5,
            "url_before": "about:blank",
            "url_after": "https://example.com/",
            "message": 'Navigated to "https://example.com"',
        }
    ]
    assert report["observation"]["elements"][0]["selector"] == "#submit"
    assert report["checks"] == [
        {
            "name": "HTTP status",
            "passed": True,
            "message": "Page returned HTTP 200",
        }
    ]
    assert report["artifacts"] == {
        "screenshot": str(screenshot_path),
        "trace": str(trace_path),
    }


def test_write_json_report_translates_file_errors(tmp_path) -> None:
    report_path = tmp_path / "missing-directory" / "report.json"
    snapshot = PageSnapshot(
        url="https://example.com/",
        status=200,
        title="Example Domain",
    )

    with pytest.raises(ReportWriteError, match="Could not write report"):
        write_json_report(
            report_path,
            "https://example.com",
            snapshot,
            [],
            tmp_path / "page.png",
            tmp_path / "trace.zip",
        )


def test_report_fails_when_an_action_failed(tmp_path) -> None:
    report_path = tmp_path / "report.json"
    snapshot = PageSnapshot(
        url="https://example.com/",
        status=200,
        title="Example Domain",
        action_results=(
            ActionResult(
                step_number=2,
                kind="click",
                status="failed",
                duration_ms=10_000.0,
                url_before="https://example.com/",
                url_after="https://example.com/",
                message="Timeout 10000ms exceeded",
            ),
        ),
    )

    write_json_report(
        report_path,
        "https://example.com",
        snapshot,
        [],
        tmp_path / "page.png",
        tmp_path / "trace.zip",
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["passed"] is False
    assert report["actions"][0]["status"] == "failed"


def test_report_fails_and_records_steps_when_agent_is_blocked(tmp_path) -> None:
    report_path = tmp_path / "report.json"
    snapshot = PageSnapshot(
        url="https://example.com/",
        status=200,
        title="Example Domain",
    )
    agent_run = AgentRunResult(
        status=AgentStatus.BLOCKED,
        reason="No matching control is visible",
        steps=(
            AgentStepResult(
                step_number=2,
                url="https://example.com/",
                decision_status=DecisionStatus.BLOCKED,
                action_kind=None,
                selector=None,
                reason="No matching control is visible",
                execution_status=None,
            ),
        ),
        action_results=(),
    )

    write_json_report(
        report_path,
        "https://example.com",
        snapshot,
        [],
        tmp_path / "page.png",
        tmp_path / "trace.zip",
        agent_run,
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["passed"] is False
    assert report["agent"] == {
        "status": "blocked",
        "reason": "No matching control is visible",
        "recoveries_used": 0,
        "verification_retries_used": 0,
        "steps": [
            {
                "step_number": 2,
                "url": "https://example.com/",
                "decision_status": "blocked",
                "action_kind": None,
                "selector": None,
                "reason": "No matching control is visible",
                "execution_status": None,
                "execution_message": None,
                "verification_results": [],
            }
        ],
    }


def test_report_passes_when_agent_recovers_and_completes(tmp_path) -> None:
    report_path = tmp_path / "report.json"
    failed_action = ActionResult(
        step_number=2,
        kind="click",
        status="failed",
        duration_ms=10_000.0,
        url_before="https://example.com/",
        url_after="https://example.com/",
        message="First selector timed out",
    )
    snapshot = PageSnapshot(
        url="https://example.com/complete",
        status=200,
        title="Complete",
        action_results=(failed_action,),
    )
    agent_run = AgentRunResult(
        status=AgentStatus.COMPLETE,
        reason="Goal reached with another control",
        steps=(),
        action_results=(failed_action,),
        recoveries_used=1,
    )

    write_json_report(
        report_path,
        "https://example.com",
        snapshot,
        [],
        tmp_path / "page.png",
        tmp_path / "trace.zip",
        agent_run,
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["passed"] is True
    assert report["actions"][0]["status"] == "failed"
    assert report["agent"]["status"] == "complete"
    assert report["agent"]["recoveries_used"] == 1


def make_suite_run_result() -> SuiteRunResult:
    suite = SuiteDefinition(
        url="https://example.com",
        request="Run baseline checks",
        tests=(
            SuiteCase(
                test_id="page-load",
                name="Page loads successfully",
                kind=SuiteTestKind.PAGE_LOAD,
            ),
        ),
    )
    return SuiteRunResult(
        suite=suite,
        results=(
            SuiteCaseResult(
                test_id="page-load",
                kind=SuiteTestKind.PAGE_LOAD,
                status=CaseStatus.PASSED,
                duration_ms=12.5,
                message="Page returned HTTP 200",
                checks=(
                    CheckResult(
                        name="HTTP status",
                        passed=True,
                        message="Page returned HTTP 200",
                    ),
                ),
            ),
        ),
    )


def test_write_suite_json_report_saves_each_case(tmp_path) -> None:
    report_path = tmp_path / "suite-report.json"
    artifact_directory = tmp_path / "artifacts"

    write_suite_json_report(
        report_path,
        make_suite_run_result(),
        artifact_directory,
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report == {
        "requested_url": "https://example.com",
        "request": "Run baseline checks",
        "passed": True,
        "tests": [
            {
                "test_id": "page-load",
                "name": "Page loads successfully",
                "kind": "page_load",
                "goal": None,
                "status": "passed",
                "duration_ms": 12.5,
                "message": "Page returned HTTP 200",
                "checks": [
                    {
                        "name": "HTTP status",
                        "passed": True,
                        "message": "Page returned HTTP 200",
                    }
                ],
            }
        ],
        "artifacts": {
            "directory": str(artifact_directory),
        },
    }


def test_write_suite_json_report_translates_file_errors(tmp_path) -> None:
    report_path = tmp_path / "missing-directory" / "report.json"

    with pytest.raises(ReportWriteError, match="Could not write report"):
        write_suite_json_report(
            report_path,
            make_suite_run_result(),
            tmp_path / "artifacts",
        )


def test_write_suite_json_report_includes_budget_snapshot(tmp_path) -> None:
    report_path = tmp_path / "suite-report.json"
    policy = SuiteExecutionPolicy(
        max_tests=4,
        max_browser_goals=1,
        max_ai_requests=3,
        max_browser_runs=2,
        max_duration_seconds=30.0,
    )
    budget = SuiteBudgetTracker(policy, clock=lambda: 10.0)
    budget.consume_ai_request()
    budget.consume_browser_run()

    write_suite_json_report(
        report_path,
        make_suite_run_result(),
        tmp_path / "artifacts",
        budget_snapshot=budget.snapshot(),
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["budget"] == {
        "limits": {
            "max_tests": 4,
            "max_browser_goals": 1,
            "max_ai_requests": 3,
            "max_browser_runs": 2,
            "max_duration_seconds": 30.0,
            "stop_on_provider_quota": True,
        },
        "usage": {
            "ai_requests": 1,
            "browser_runs": 1,
            "elapsed_seconds": 0.0,
        },
        "exhausted": False,
        "reason": None,
    }
