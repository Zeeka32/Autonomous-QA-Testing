import pytest

from autonomous_qa.budgets import (
    SuiteBudgetTracker,
    SuiteExecutionPolicy,
)
from autonomous_qa.models import CheckResult
from autonomous_qa.suite_runner import (
    SuiteRunnerError,
    TestExecutionError as CaseExecutionError,
    run_test_suite,
)
from autonomous_qa.suites import (
    TestCase as SuiteCase,
    TestKind as SuiteTestKind,
    TestOutcome as CaseOutcome,
    TestStatus as CaseStatus,
    TestSuite as SuiteDefinition,
)


def make_suite() -> SuiteDefinition:
    return SuiteDefinition(
        url="https://example.com",
        request="Run basic checks and open the menu",
        tests=(
            SuiteCase(
                test_id="page-load",
                name="Page loads successfully",
                kind=SuiteTestKind.PAGE_LOAD,
            ),
            SuiteCase(
                test_id="page-title",
                name="Page has a title",
                kind=SuiteTestKind.TITLE_PRESENT,
            ),
            SuiteCase(
                test_id="open-menu",
                name="Open the menu",
                kind=SuiteTestKind.BROWSER_GOAL,
                goal="Open the menu",
            ),
        ),
    )


def test_runner_executes_every_case_in_suite_order() -> None:
    suite = make_suite()
    calls = []

    def page_load(url, test):
        calls.append((url, test.test_id))
        return CaseOutcome(
            status=CaseStatus.PASSED,
            message="Page returned HTTP 200",
            checks=(
                CheckResult(
                    name="HTTP status",
                    passed=True,
                    message="Page returned HTTP 200",
                ),
            ),
        )

    def page_title(url, test):
        calls.append((url, test.test_id))
        return CaseOutcome(
            status=CaseStatus.FAILED,
            message="Page title is empty",
            checks=(
                CheckResult(
                    name="Page title",
                    passed=False,
                    message="Page title is empty",
                ),
            ),
        )

    def browser_goal(url, test):
        calls.append((url, test.test_id))
        raise CaseExecutionError("Browser navigation timed out")

    result = run_test_suite(
        suite,
        {
            SuiteTestKind.PAGE_LOAD: page_load,
            SuiteTestKind.TITLE_PRESENT: page_title,
            SuiteTestKind.BROWSER_GOAL: browser_goal,
        },
    )

    assert calls == [
        ("https://example.com", "page-load"),
        ("https://example.com", "page-title"),
        ("https://example.com", "open-menu"),
    ]
    assert [case.status for case in result.results] == [
        CaseStatus.PASSED,
        CaseStatus.FAILED,
        CaseStatus.ERROR,
    ]
    assert result.results[2].message == "Browser navigation timed out"
    assert all(case.duration_ms >= 0 for case in result.results)
    assert result.passed is False


def test_runner_reports_success_when_every_case_passes() -> None:
    suite = make_suite()

    result = run_test_suite(
        suite,
        {
            kind: lambda url, test: CaseOutcome(
                status=CaseStatus.PASSED,
                message=f'{test.name} passed for "{url}"',
            )
            for kind in SuiteTestKind
        },
    )

    assert result.passed is True
    assert all(case.passed for case in result.results)


def test_runner_rejects_missing_executors_before_running_cases() -> None:
    suite = make_suite()
    calls = []

    def page_load(url, test):
        calls.append(test.test_id)
        return CaseOutcome(
            status=CaseStatus.PASSED,
            message="Page loaded",
        )

    with pytest.raises(SuiteRunnerError, match="browser_goal, title_present"):
        run_test_suite(
            suite,
            {SuiteTestKind.PAGE_LOAD: page_load},
        )

    assert calls == []


def test_runner_rejects_invalid_executor_outcomes() -> None:
    suite = SuiteDefinition(
        url="https://example.com",
        tests=(
            SuiteCase(
                test_id="page-load",
                name="Page loads successfully",
                kind=SuiteTestKind.PAGE_LOAD,
            ),
        ),
    )

    with pytest.raises(SuiteRunnerError, match="invalid outcome"):
        run_test_suite(
            suite,
            {SuiteTestKind.PAGE_LOAD: lambda url, test: True},
        )


def test_runner_does_not_hide_unexpected_executor_bugs() -> None:
    suite = SuiteDefinition(
        url="https://example.com",
        tests=(
            SuiteCase(
                test_id="page-load",
                name="Page loads successfully",
                kind=SuiteTestKind.PAGE_LOAD,
            ),
        ),
    )

    def broken_executor(url, test):
        raise ValueError("programming bug")

    with pytest.raises(ValueError, match="programming bug"):
        run_test_suite(
            suite,
            {SuiteTestKind.PAGE_LOAD: broken_executor},
        )


def test_runner_skips_entire_suite_when_shape_budget_is_exceeded() -> None:
    suite = make_suite()
    calls = []

    def execute(url, test):
        calls.append(test.test_id)
        return CaseOutcome(
            status=CaseStatus.PASSED,
            message="Passed",
        )

    result = run_test_suite(
        suite,
        {kind: execute for kind in SuiteTestKind},
        budget=SuiteBudgetTracker(
            SuiteExecutionPolicy(max_tests=2)
        ),
    )

    assert calls == []
    assert [case.status for case in result.results] == [
        CaseStatus.SKIPPED,
        CaseStatus.SKIPPED,
        CaseStatus.SKIPPED,
    ]
    assert all(
        "test budget exhausted" in case.message
        for case in result.results
    )


def test_runner_preserves_results_before_runtime_budget_exhaustion() -> None:
    suite = make_suite()
    budget = SuiteBudgetTracker(
        SuiteExecutionPolicy(max_ai_requests=0)
    )
    calls = []

    def page_load(url, test):
        calls.append(test.test_id)
        return CaseOutcome(
            status=CaseStatus.PASSED,
            message="Page loaded",
        )

    def page_title(url, test):
        calls.append(test.test_id)
        budget.consume_ai_request()
        raise AssertionError("budget call must raise")

    def browser_goal(url, test):
        calls.append(test.test_id)
        raise AssertionError("remaining executor must not run")

    result = run_test_suite(
        suite,
        {
            SuiteTestKind.PAGE_LOAD: page_load,
            SuiteTestKind.TITLE_PRESENT: page_title,
            SuiteTestKind.BROWSER_GOAL: browser_goal,
        },
        budget=budget,
    )

    assert calls == ["page-load", "page-title"]
    assert [case.status for case in result.results] == [
        CaseStatus.PASSED,
        CaseStatus.SKIPPED,
        CaseStatus.SKIPPED,
    ]
    assert "AI-request budget exhausted" in result.results[1].message
    assert result.results[1].duration_ms >= 0
    assert result.results[2].duration_ms == 0
