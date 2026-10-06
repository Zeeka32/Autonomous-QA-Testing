from collections.abc import Callable, Mapping
from time import perf_counter

from .budgets import SuiteBudgetExceeded, SuiteBudgetTracker
from .suites import (
    MAX_RESULT_MESSAGE_LENGTH,
    SuiteRunResult,
    TestCase,
    TestCaseResult,
    TestKind,
    TestOutcome,
    TestStatus,
    TestSuite,
)


TestExecutor = Callable[[str, TestCase], TestOutcome]
ResultReporter = Callable[[TestCaseResult], None]


class SuiteRunnerError(RuntimeError):
    """Raised when the suite runner or an executor violates its contract."""


class TestExecutionError(RuntimeError):
    """Raised when a test cannot be executed normally."""


def _skipped_result(
    test: TestCase,
    message: str,
    duration_ms: float = 0.0,
) -> TestCaseResult:
    return TestCaseResult(
        test_id=test.test_id,
        kind=test.kind,
        status=TestStatus.SKIPPED,
        duration_ms=duration_ms,
        message=message,
    )


def run_test_suite(
    suite: TestSuite,
    executors: Mapping[TestKind, TestExecutor],
    budget: SuiteBudgetTracker | None = None,
    on_result: ResultReporter | None = None,
) -> SuiteRunResult:
    required_kinds = {test.kind for test in suite.tests}
    missing_kinds = required_kinds - set(executors)
    if missing_kinds:
        missing = ", ".join(sorted(str(kind) for kind in missing_kinds))
        raise SuiteRunnerError(f"Missing test executors for: {missing}")

    if budget is not None:
        try:
            budget.validate_suite(
                test_count=len(suite.tests),
                browser_goal_count=sum(
                    test.kind is TestKind.BROWSER_GOAL
                    for test in suite.tests
                ),
            )
        except SuiteBudgetExceeded as error:
            message = str(error)
            suite_run = SuiteRunResult(
                suite=suite,
                results=tuple(
                    _skipped_result(test, message)
                    for test in suite.tests
                ),
            )
            if on_result is not None:
                for result in suite_run.results:
                    on_result(result)
            return suite_run

    results: list[TestCaseResult] = []

    def record(result: TestCaseResult) -> None:
        results.append(result)
        if on_result is not None:
            on_result(result)

    for index, test in enumerate(suite.tests):
        if budget is not None:
            try:
                budget.check_duration()
            except SuiteBudgetExceeded as error:
                message = str(error)
                for remaining_test in suite.tests[index:]:
                    record(_skipped_result(remaining_test, message))
                break

        started_at = perf_counter()
        try:
            outcome = executors[test.kind](suite.url, test)
        except SuiteBudgetExceeded as error:
            duration_ms = (perf_counter() - started_at) * 1_000
            message = str(error)
            record(_skipped_result(test, message, duration_ms))
            for remaining_test in suite.tests[index + 1:]:
                record(_skipped_result(remaining_test, message))
            break
        except TestExecutionError as error:
            error_message = str(error).strip() or "Test execution failed"
            outcome = TestOutcome(
                status=TestStatus.ERROR,
                message=error_message[:MAX_RESULT_MESSAGE_LENGTH],
            )
        duration_ms = (perf_counter() - started_at) * 1_000

        if not isinstance(outcome, TestOutcome):
            raise SuiteRunnerError(
                f'Executor for "{test.test_id}" returned an invalid outcome'
            )

        record(
            TestCaseResult(
                test_id=test.test_id,
                kind=test.kind,
                status=outcome.status,
                duration_ms=duration_ms,
                message=outcome.message,
                checks=outcome.checks,
            )
        )

    return SuiteRunResult(suite=suite, results=tuple(results))
