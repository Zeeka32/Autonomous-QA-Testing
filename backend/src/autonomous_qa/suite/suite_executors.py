from collections.abc import Callable, Mapping
from pathlib import Path

from ..agent import AgentStatus, AgentStepReporter, DecisionPlanner
from .budgets import SuiteBudgetTracker
from ..browser.checks import check_http_status, check_title, run_checks
from ..models import CheckResult, PageSnapshot
from ..planner import PlannerError, PlannerQuotaError
from ..plans import ActionPlan, NavigateAction, PlanAssertion
from ..browser.runner import (
    AccessibilityInspectionResult,
    AgentInspectionResult,
    CriteriaGenerator,
    PageInspectionError,
    inspect_accessibility,
    inspect_page,
    inspect_page_with_agent,
)
from .suite_runner import TestExecutionError, TestExecutor
from .suites import TestCase, TestKind, TestOutcome, TestStatus


PageInspector = Callable[[ActionPlan, Path, Path], PageSnapshot]
AccessibilityInspector = Callable[
    [str, Path, Path],
    AccessibilityInspectionResult,
]
AgentInspector = Callable[
    [
        str,
        str,
        DecisionPlanner,
        tuple[PlanAssertion, ...],
        Path,
        Path,
        CriteriaGenerator | None,
        AgentStepReporter | None,
    ],
    AgentInspectionResult,
]


def _outcome_from_check(check: CheckResult) -> TestOutcome:
    return TestOutcome(
        status=(TestStatus.PASSED if check.passed else TestStatus.FAILED),
        message=check.message,
        checks=(check,),
    )


def create_suite_executors(
    artifact_directory: Path,
    planner: DecisionPlanner | None = None,
    criteria_generator: CriteriaGenerator | None = None,
    agent_step_reporter: AgentStepReporter | None = None,
    page_inspector: PageInspector = inspect_page,
    accessibility_inspector: AccessibilityInspector = inspect_accessibility,
    agent_inspector: AgentInspector = inspect_page_with_agent,
    initial_snapshots: Mapping[str, PageSnapshot] | None = None,
    budget: SuiteBudgetTracker | None = None,
) -> dict[TestKind, TestExecutor]:
    """Build suite executors around the existing browser runners."""

    baseline_snapshots = dict(initial_snapshots or {})

    def get_baseline_snapshot(url: str) -> PageSnapshot:
        if url not in baseline_snapshots:
            artifact_directory.mkdir(parents=True, exist_ok=True)
            if budget is not None:
                budget.consume_browser_run()
            plan = ActionPlan(actions=(NavigateAction(url=url),))
            try:
                baseline_snapshots[url] = page_inspector(
                    plan,
                    artifact_directory / "baseline-screenshot.png",
                    artifact_directory / "baseline-trace.zip",
                )
            except PageInspectionError as error:
                raise TestExecutionError(str(error)) from error
        return baseline_snapshots[url]

    def execute_page_load(url: str, test: TestCase) -> TestOutcome:
        return _outcome_from_check(
            check_http_status(get_baseline_snapshot(url))
        )

    def execute_title_present(url: str, test: TestCase) -> TestOutcome:
        return _outcome_from_check(check_title(get_baseline_snapshot(url)))

    def execute_accessibility(
        url: str,
        test: TestCase,
    ) -> TestOutcome:
        artifact_directory.mkdir(parents=True, exist_ok=True)
        if budget is not None:
            budget.consume_browser_run()
        try:
            inspection = accessibility_inspector(
                url,
                artifact_directory / f"{test.test_id}-screenshot.png",
                artifact_directory / f"{test.test_id}-trace.zip",
            )
        except PageInspectionError as error:
            raise TestExecutionError(str(error)) from error

        status_check = check_http_status(inspection.snapshot)
        checks = (status_check,) + inspection.checks
        failed_accessibility_checks = tuple(
            check for check in inspection.checks if not check.passed
        )
        passed = status_check.passed and not failed_accessibility_checks
        if not status_check.passed:
            message = status_check.message
        elif failed_accessibility_checks:
            message = (
                f"{len(failed_accessibility_checks)} basic accessibility "
                "checks failed"
            )
        else:
            message = "Basic accessibility checks passed"
        return TestOutcome(
            status=(
                TestStatus.PASSED
                if passed
                else TestStatus.FAILED
            ),
            message=message,
            checks=checks,
        )

    executors: dict[TestKind, TestExecutor] = {
        TestKind.PAGE_LOAD: execute_page_load,
        TestKind.TITLE_PRESENT: execute_title_present,
        TestKind.ACCESSIBILITY: execute_accessibility,
    }

    if planner is not None:

        def execute_browser_goal(
            url: str,
            test: TestCase,
        ) -> TestOutcome:
            if test.goal is None:
                raise TestExecutionError(
                    "Browser-goal test does not contain a goal"
                )
            artifact_directory.mkdir(parents=True, exist_ok=True)
            if budget is not None:
                budget.consume_browser_run()
            try:
                inspection = agent_inspector(
                    url,
                    test.goal,
                    planner,
                    test.assertions,
                    artifact_directory / f"{test.test_id}-screenshot.png",
                    artifact_directory / f"{test.test_id}-trace.zip",
                    criteria_generator,
                    agent_step_reporter,
                )
            except PlannerQuotaError as error:
                if (
                    budget is not None
                    and budget.policy.stop_on_provider_quota
                ):
                    budget.stop(
                        "AI provider quota or rate limit was reached"
                    )
                raise TestExecutionError(str(error)) from error
            except (PageInspectionError, PlannerError) as error:
                raise TestExecutionError(str(error)) from error

            checks = tuple(run_checks(inspection.snapshot))
            passed = (
                inspection.agent_run.status is AgentStatus.COMPLETE
                and all(check.passed for check in checks)
            )
            return TestOutcome(
                status=(TestStatus.PASSED if passed else TestStatus.FAILED),
                message=inspection.agent_run.reason,
                checks=checks,
            )

        executors[TestKind.BROWSER_GOAL] = execute_browser_goal

    return executors
