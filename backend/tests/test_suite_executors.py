from autonomous_qa.agent import AgentRunResult, AgentStatus
from autonomous_qa.suite.budgets import (
    SuiteBudgetTracker,
    SuiteExecutionPolicy,
)
from autonomous_qa.models import CheckResult, PageSnapshot
from autonomous_qa.planner import PlannerError, PlannerQuotaError
from autonomous_qa.plans import TitleContainsAssertion
from autonomous_qa.browser.runner import (
    AccessibilityInspectionResult,
    AgentInspectionResult,
    PageInspectionError,
)
from autonomous_qa.suite.suite_executors import create_suite_executors
from autonomous_qa.suite.suite_runner import run_test_suite
from autonomous_qa.suite.suites import (
    TestCase as SuiteCase,
    TestKind as SuiteTestKind,
    TestStatus as CaseStatus,
    TestSuite as SuiteDefinition,
)


def make_snapshot(
    *,
    status: int | None = 200,
    title: str = "Example Domain",
    assertion_results: tuple[CheckResult, ...] = (),
) -> PageSnapshot:
    return PageSnapshot(
        url="https://example.com",
        status=status,
        title=title,
        assertion_results=assertion_results,
    )


def make_agent_inspection(
    status: AgentStatus,
    reason: str,
    snapshot: PageSnapshot | None = None,
) -> AgentInspectionResult:
    return AgentInspectionResult(
        snapshot=snapshot or make_snapshot(),
        agent_run=AgentRunResult(
            status=status,
            reason=reason,
            steps=(),
            action_results=(),
        ),
    )


def test_deterministic_executors_share_one_baseline_inspection(
    tmp_path,
) -> None:
    calls = []

    def inspect(plan, screenshot_path, trace_path):
        calls.append((plan, screenshot_path, trace_path))
        return make_snapshot()

    suite = SuiteDefinition(
        url="https://example.com",
        tests=(
            SuiteCase(
                test_id="page-load",
                name="Page loads",
                kind=SuiteTestKind.PAGE_LOAD,
            ),
            SuiteCase(
                test_id="page-title",
                name="Page has a title",
                kind=SuiteTestKind.TITLE_PRESENT,
            ),
        ),
    )

    result = run_test_suite(
        suite,
        create_suite_executors(tmp_path, page_inspector=inspect),
    )

    assert len(calls) == 1
    plan, screenshot_path, trace_path = calls[0]
    assert plan.actions[0].url == "https://example.com"
    assert screenshot_path == tmp_path / "baseline-screenshot.png"
    assert trace_path == tmp_path / "baseline-trace.zip"
    assert [case.status for case in result.results] == [
        CaseStatus.PASSED,
        CaseStatus.PASSED,
    ]
    assert [case.checks[0].name for case in result.results] == [
        "HTTP status",
        "Page title",
    ]


def test_deterministic_executors_return_failed_checks(tmp_path) -> None:
    def inspect(plan, screenshot_path, trace_path):
        return make_snapshot(status=503, title="   ")

    suite = SuiteDefinition(
        url="https://example.com",
        tests=(
            SuiteCase(
                test_id="page-load",
                name="Page loads",
                kind=SuiteTestKind.PAGE_LOAD,
            ),
            SuiteCase(
                test_id="page-title",
                name="Page has a title",
                kind=SuiteTestKind.TITLE_PRESENT,
            ),
        ),
    )

    result = run_test_suite(
        suite,
        create_suite_executors(tmp_path, page_inspector=inspect),
    )

    assert [case.status for case in result.results] == [
        CaseStatus.FAILED,
        CaseStatus.FAILED,
    ]
    assert result.results[0].message == "Page returned HTTP 503"
    assert result.results[1].message == "Page title is empty"


def test_browser_goal_executor_passes_dependencies_and_artifact_paths(
    tmp_path,
) -> None:
    calls = []
    assertion = TitleContainsAssertion(value="Done")
    expected_check = CheckResult(
        name="Expected title",
        passed=True,
        message='Page title "Done" contains "Done"',
    )

    def planner(*args):
        raise AssertionError("fake agent inspector should not call planner")

    def generate_criteria(*args):
        raise AssertionError("fake agent inspector should not call generator")

    def report_step(step):
        raise AssertionError("fake agent inspector should not report steps")

    def inspect_agent(*args):
        calls.append(args)
        return make_agent_inspection(
            AgentStatus.COMPLETE,
            "The requested state was reached",
            make_snapshot(
                title="Done",
                assertion_results=(expected_check,),
            ),
        )

    test = SuiteCase(
        test_id="finish-workflow",
        name="Finish the workflow",
        kind=SuiteTestKind.BROWSER_GOAL,
        goal="Finish the workflow",
        assertions=(assertion,),
    )
    suite = SuiteDefinition(
        url="https://example.com",
        tests=(test,),
    )

    result = run_test_suite(
        suite,
        create_suite_executors(
            tmp_path,
            planner=planner,
            criteria_generator=generate_criteria,
            agent_step_reporter=report_step,
            agent_inspector=inspect_agent,
        ),
    )

    assert calls == [
        (
            "https://example.com",
            "Finish the workflow",
            planner,
            (assertion,),
            tmp_path / "finish-workflow-screenshot.png",
            tmp_path / "finish-workflow-trace.zip",
            generate_criteria,
            report_step,
        )
    ]
    assert result.results[0].status is CaseStatus.PASSED
    assert [check.name for check in result.results[0].checks] == [
        "HTTP status",
        "Page title",
        "Expected title",
    ]


def test_incomplete_browser_goal_is_a_failed_test(tmp_path) -> None:
    def planner(*args):
        raise AssertionError("fake agent inspector should not call planner")

    def inspect_agent(*args):
        return make_agent_inspection(
            AgentStatus.BLOCKED,
            "The required control was not present",
        )

    suite = SuiteDefinition(
        url="https://example.com",
        tests=(
            SuiteCase(
                test_id="open-menu",
                name="Open the menu",
                kind=SuiteTestKind.BROWSER_GOAL,
                goal="Open the menu",
            ),
        ),
    )

    result = run_test_suite(
        suite,
        create_suite_executors(
            tmp_path,
            planner=planner,
            agent_inspector=inspect_agent,
        ),
    )

    assert result.results[0].status is CaseStatus.FAILED
    assert result.results[0].message == "The required control was not present"


def test_expected_execution_errors_are_recorded_and_suite_continues(
    tmp_path,
) -> None:
    def planner(*args):
        raise AssertionError("fake agent inspector should not call planner")

    def inspect_agent(*args):
        raise PlannerError("AI provider quota exceeded")

    def inspect_page(plan, screenshot_path, trace_path):
        return make_snapshot()

    suite = SuiteDefinition(
        url="https://example.com",
        tests=(
            SuiteCase(
                test_id="open-menu",
                name="Open the menu",
                kind=SuiteTestKind.BROWSER_GOAL,
                goal="Open the menu",
            ),
            SuiteCase(
                test_id="page-load",
                name="Page loads",
                kind=SuiteTestKind.PAGE_LOAD,
            ),
        ),
    )

    result = run_test_suite(
        suite,
        create_suite_executors(
            tmp_path,
            planner=planner,
            page_inspector=inspect_page,
            agent_inspector=inspect_agent,
        ),
    )

    assert [case.status for case in result.results] == [
        CaseStatus.ERROR,
        CaseStatus.PASSED,
    ]
    assert result.results[0].message == "AI provider quota exceeded"


def test_page_inspection_error_becomes_an_error_outcome(tmp_path) -> None:
    def inspect(plan, screenshot_path, trace_path):
        raise PageInspectionError("Browser could not start")

    suite = SuiteDefinition(
        url="https://example.com",
        tests=(
            SuiteCase(
                test_id="page-load",
                name="Page loads",
                kind=SuiteTestKind.PAGE_LOAD,
            ),
        ),
    )

    result = run_test_suite(
        suite,
        create_suite_executors(tmp_path, page_inspector=inspect),
    )

    assert result.results[0].status is CaseStatus.ERROR
    assert result.results[0].message == "Browser could not start"


def test_browser_goal_executor_is_only_available_with_a_planner(
    tmp_path,
) -> None:
    executors = create_suite_executors(tmp_path)

    assert set(executors) == {
        SuiteTestKind.PAGE_LOAD,
        SuiteTestKind.TITLE_PRESENT,
        SuiteTestKind.ACCESSIBILITY,
    }


def test_deterministic_executors_reuse_an_initial_snapshot(tmp_path) -> None:
    initial_snapshot = make_snapshot(status=204, title="Initial title")

    def inspect(plan, screenshot_path, trace_path):
        raise AssertionError("initial snapshot should prevent another inspection")

    suite = SuiteDefinition(
        url="https://example.com",
        tests=(
            SuiteCase(
                test_id="page-load",
                name="Page loads",
                kind=SuiteTestKind.PAGE_LOAD,
            ),
            SuiteCase(
                test_id="page-title",
                name="Page has a title",
                kind=SuiteTestKind.TITLE_PRESENT,
            ),
        ),
    )

    result = run_test_suite(
        suite,
        create_suite_executors(
            tmp_path,
            page_inspector=inspect,
            initial_snapshots={
                "https://example.com": initial_snapshot,
            },
        ),
    )

    assert result.passed is True
    assert result.results[0].message == "Page returned HTTP 204"
    assert result.results[1].message == 'Page title is "Initial title"'


def test_accessibility_executor_returns_structured_failures(tmp_path) -> None:
    calls = []
    failed_check = CheckResult(
        name="Form control names",
        passed=False,
        message="1 form control is missing an accessible name: input#email",
    )

    def inspect_accessibility(url, screenshot_path, trace_path):
        calls.append((url, screenshot_path, trace_path))
        return AccessibilityInspectionResult(
            snapshot=make_snapshot(),
            checks=(
                CheckResult(
                    name="Document language",
                    passed=True,
                    message='Document language is "en"',
                ),
                failed_check,
            ),
        )

    suite = SuiteDefinition(
        url="https://example.com",
        tests=(
            SuiteCase(
                test_id="accessibility",
                name="Run basic accessibility checks",
                kind=SuiteTestKind.ACCESSIBILITY,
            ),
        ),
    )

    result = run_test_suite(
        suite,
        create_suite_executors(
            tmp_path,
            accessibility_inspector=inspect_accessibility,
        ),
    )

    assert calls == [
        (
            "https://example.com",
            tmp_path / "accessibility-screenshot.png",
            tmp_path / "accessibility-trace.zip",
        )
    ]
    assert result.results[0].status is CaseStatus.FAILED
    assert result.results[0].message == (
        "1 basic accessibility checks failed"
    )
    assert [check.name for check in result.results[0].checks] == [
        "HTTP status",
        "Document language",
        "Form control names",
    ]


def test_accessibility_executor_passes_when_all_checks_pass(tmp_path) -> None:
    def inspect_accessibility(url, screenshot_path, trace_path):
        return AccessibilityInspectionResult(
            snapshot=make_snapshot(),
            checks=(
                CheckResult(
                    name="Document language",
                    passed=True,
                    message='Document language is "en"',
                ),
            ),
        )

    suite = SuiteDefinition(
        url="https://example.com",
        tests=(
            SuiteCase(
                test_id="accessibility",
                name="Run basic accessibility checks",
                kind=SuiteTestKind.ACCESSIBILITY,
            ),
        ),
    )

    result = run_test_suite(
        suite,
        create_suite_executors(
            tmp_path,
            accessibility_inspector=inspect_accessibility,
        ),
    )

    assert result.results[0].status is CaseStatus.PASSED
    assert result.results[0].message == (
        "Basic accessibility checks passed"
    )


def test_accessibility_inspection_error_becomes_error_outcome(
    tmp_path,
) -> None:
    def inspect_accessibility(url, screenshot_path, trace_path):
        raise PageInspectionError("Accessibility browser failed")

    suite = SuiteDefinition(
        url="https://example.com",
        tests=(
            SuiteCase(
                test_id="accessibility",
                name="Run basic accessibility checks",
                kind=SuiteTestKind.ACCESSIBILITY,
            ),
        ),
    )

    result = run_test_suite(
        suite,
        create_suite_executors(
            tmp_path,
            accessibility_inspector=inspect_accessibility,
        ),
    )

    assert result.results[0].status is CaseStatus.ERROR
    assert result.results[0].message == "Accessibility browser failed"


def test_cached_deterministic_checks_consume_one_browser_run(
    tmp_path,
) -> None:
    budget = SuiteBudgetTracker(SuiteExecutionPolicy())
    suite = SuiteDefinition(
        url="https://example.com",
        tests=(
            SuiteCase(
                test_id="page-load",
                name="Page loads",
                kind=SuiteTestKind.PAGE_LOAD,
            ),
            SuiteCase(
                test_id="page-title",
                name="Page has a title",
                kind=SuiteTestKind.TITLE_PRESENT,
            ),
        ),
    )

    result = run_test_suite(
        suite,
        create_suite_executors(
            tmp_path,
            page_inspector=lambda *args: make_snapshot(),
            budget=budget,
        ),
        budget=budget,
    )

    assert result.passed is True
    assert budget.snapshot().browser_runs_used == 1


def test_browser_run_exhaustion_skips_current_and_remaining_tests(
    tmp_path,
) -> None:
    inspection_calls = []

    def inspect(*args):
        inspection_calls.append(args)
        return make_snapshot()

    budget = SuiteBudgetTracker(
        SuiteExecutionPolicy(max_browser_runs=0)
    )
    suite = SuiteDefinition(
        url="https://example.com",
        tests=(
            SuiteCase(
                test_id="page-load",
                name="Page loads",
                kind=SuiteTestKind.PAGE_LOAD,
            ),
            SuiteCase(
                test_id="page-title",
                name="Page has a title",
                kind=SuiteTestKind.TITLE_PRESENT,
            ),
        ),
    )

    result = run_test_suite(
        suite,
        create_suite_executors(
            tmp_path,
            page_inspector=inspect,
            budget=budget,
        ),
        budget=budget,
    )

    assert inspection_calls == []
    assert [case.status for case in result.results] == [
        CaseStatus.SKIPPED,
        CaseStatus.SKIPPED,
    ]
    assert "browser-run budget exhausted" in result.results[0].message


def test_provider_quota_stops_and_skips_the_rest_of_the_suite(
    tmp_path,
) -> None:
    def planner(*args):
        raise AssertionError("fake agent inspector should not call planner")

    def inspect_agent(*args):
        raise PlannerQuotaError("Provider returned HTTP 429")

    budget = SuiteBudgetTracker(SuiteExecutionPolicy())
    suite = SuiteDefinition(
        url="https://example.com",
        tests=(
            SuiteCase(
                test_id="open-menu",
                name="Open the menu",
                kind=SuiteTestKind.BROWSER_GOAL,
                goal="Open the menu",
            ),
            SuiteCase(
                test_id="page-load",
                name="Page loads",
                kind=SuiteTestKind.PAGE_LOAD,
            ),
        ),
    )

    result = run_test_suite(
        suite,
        create_suite_executors(
            tmp_path,
            planner=planner,
            agent_inspector=inspect_agent,
            budget=budget,
        ),
        budget=budget,
    )

    assert [case.status for case in result.results] == [
        CaseStatus.SKIPPED,
        CaseStatus.SKIPPED,
    ]
    assert result.results[0].message == (
        "AI provider quota or rate limit was reached"
    )
    assert budget.snapshot().exhausted is True
