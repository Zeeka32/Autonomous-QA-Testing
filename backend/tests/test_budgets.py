import pytest

from autonomous_qa.suite.budgets import (
    SuiteBudgetExceeded,
    SuiteBudgetTracker,
    SuiteBudgetValidationError,
    SuiteExecutionPolicy,
)


class FakeClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value


def test_tracker_records_ai_requests_and_browser_runs() -> None:
    clock = FakeClock()
    tracker = SuiteBudgetTracker(
        SuiteExecutionPolicy(
            max_ai_requests=2,
            max_browser_runs=2,
        ),
        clock=clock,
    )

    assert tracker.consume_ai_request() == 1
    assert tracker.consume_browser_run() == 1
    clock.value += 2.5

    snapshot = tracker.snapshot()
    assert snapshot.ai_requests_used == 1
    assert snapshot.browser_runs_used == 1
    assert snapshot.elapsed_seconds == 2.5
    assert snapshot.exhausted is False


def test_tracker_stops_before_exceeding_ai_request_limit() -> None:
    tracker = SuiteBudgetTracker(
        SuiteExecutionPolicy(max_ai_requests=1)
    )

    tracker.consume_ai_request()

    with pytest.raises(SuiteBudgetExceeded, match="AI-request"):
        tracker.consume_ai_request()

    snapshot = tracker.snapshot()
    assert snapshot.ai_requests_used == 1
    assert snapshot.exhausted is True


def test_tracker_rejects_suite_larger_than_policy() -> None:
    tracker = SuiteBudgetTracker(
        SuiteExecutionPolicy(max_tests=2, max_browser_goals=1)
    )

    with pytest.raises(SuiteBudgetExceeded, match="test budget"):
        tracker.validate_suite(test_count=3, browser_goal_count=1)


def test_tracker_rejects_too_many_browser_goals() -> None:
    tracker = SuiteBudgetTracker(
        SuiteExecutionPolicy(max_tests=5, max_browser_goals=1)
    )

    with pytest.raises(SuiteBudgetExceeded, match="browser-goal"):
        tracker.validate_suite(test_count=2, browser_goal_count=2)


def test_tracker_enforces_elapsed_time() -> None:
    clock = FakeClock()
    tracker = SuiteBudgetTracker(
        SuiteExecutionPolicy(max_duration_seconds=10),
        clock=clock,
    )
    clock.value += 10

    with pytest.raises(SuiteBudgetExceeded, match="duration"):
        tracker.check_duration()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_tests", 0),
        ("max_browser_goals", -1),
        ("max_ai_requests", -1),
        ("max_browser_runs", -1),
        ("max_duration_seconds", 0),
    ],
)
def test_policy_rejects_invalid_limits(field, value) -> None:
    values = {field: value}

    with pytest.raises(SuiteBudgetValidationError):
        SuiteExecutionPolicy(**values)
