from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter


DEFAULT_MAX_SUITE_TESTS = 5
DEFAULT_MAX_BROWSER_GOALS = 2
DEFAULT_MAX_AI_REQUESTS = 10
DEFAULT_MAX_BROWSER_RUNS = 5
DEFAULT_MAX_SUITE_SECONDS = 120.0


class SuiteBudgetValidationError(ValueError):
    """Raised when suite execution limits are invalid."""


class SuiteBudgetExceeded(RuntimeError):
    """Raised when a suite consumes an execution limit."""


def _require_integer_limit(
    value: int,
    field_name: str,
    *,
    minimum: int,
) -> None:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < minimum
    ):
        raise SuiteBudgetValidationError(
            f"{field_name} must be an integer of at least {minimum}"
        )


@dataclass(frozen=True)
class SuiteExecutionPolicy:
    max_tests: int = DEFAULT_MAX_SUITE_TESTS
    max_browser_goals: int = DEFAULT_MAX_BROWSER_GOALS
    max_ai_requests: int = DEFAULT_MAX_AI_REQUESTS
    max_browser_runs: int = DEFAULT_MAX_BROWSER_RUNS
    max_duration_seconds: float = DEFAULT_MAX_SUITE_SECONDS
    stop_on_provider_quota: bool = True

    def __post_init__(self) -> None:
        _require_integer_limit(self.max_tests, "max_tests", minimum=1)
        _require_integer_limit(
            self.max_browser_goals,
            "max_browser_goals",
            minimum=0,
        )
        _require_integer_limit(
            self.max_ai_requests,
            "max_ai_requests",
            minimum=0,
        )
        _require_integer_limit(
            self.max_browser_runs,
            "max_browser_runs",
            minimum=0,
        )
        if (
            not isinstance(self.max_duration_seconds, (int, float))
            or isinstance(self.max_duration_seconds, bool)
            or self.max_duration_seconds <= 0
        ):
            raise SuiteBudgetValidationError(
                "max_duration_seconds must be a positive number"
            )
        if not isinstance(self.stop_on_provider_quota, bool):
            raise SuiteBudgetValidationError(
                "stop_on_provider_quota must be a boolean"
            )



@dataclass(frozen=True)
class SuiteBudgetSnapshot:
    policy: SuiteExecutionPolicy
    ai_requests_used: int
    browser_runs_used: int
    elapsed_seconds: float
    exhausted_reason: str | None = None

    @property
    def exhausted(self) -> bool:
        return self.exhausted_reason is not None


class SuiteBudgetTracker:
    def __init__(
        self,
        policy: SuiteExecutionPolicy,
        clock: Callable[[], float] = perf_counter,
    ) -> None:
        self.policy = policy
        self._clock = clock
        self._started_at = clock()
        self._ai_requests_used = 0
        self._browser_runs_used = 0
        self._exhausted_reason: str | None = None

    @property
    def exhausted_reason(self) -> str | None:
        return self._exhausted_reason

    def elapsed_seconds(self) -> float:
        return max(0.0, self._clock() - self._started_at)

    def _exhaust(self, reason: str) -> None:
        if self._exhausted_reason is None:
            self._exhausted_reason = reason
        raise SuiteBudgetExceeded(self._exhausted_reason)

    def stop(self, reason: str) -> None:
        self._exhaust(reason)

    def check_duration(self) -> None:
        if self._exhausted_reason is not None:
            raise SuiteBudgetExceeded(self._exhausted_reason)
        if self.elapsed_seconds() >= self.policy.max_duration_seconds:
            self._exhaust(
                "Suite duration budget exhausted "
                f"({self.policy.max_duration_seconds:g} seconds)"
            )

    def validate_suite(
        self,
        *,
        test_count: int,
        browser_goal_count: int,
    ) -> None:
        self.check_duration()
        if test_count > self.policy.max_tests:
            self._exhaust(
                "Suite test budget exhausted "
                f"({test_count} requested, "
                f"maximum {self.policy.max_tests})"
            )
        if browser_goal_count > self.policy.max_browser_goals:
            self._exhaust(
                "Suite browser-goal budget exhausted "
                f"({browser_goal_count} requested, "
                f"maximum {self.policy.max_browser_goals})"
            )

    def consume_ai_request(self) -> int:
        self.check_duration()
        if self._ai_requests_used >= self.policy.max_ai_requests:
            self._exhaust(
                "Suite AI-request budget exhausted "
                f"(maximum {self.policy.max_ai_requests})"
            )
        self._ai_requests_used += 1
        return self._ai_requests_used

    def consume_browser_run(self) -> int:
        self.check_duration()
        if self._browser_runs_used >= self.policy.max_browser_runs:
            self._exhaust(
                "Suite browser-run budget exhausted "
                f"(maximum {self.policy.max_browser_runs})"
            )
        self._browser_runs_used += 1
        return self._browser_runs_used

    def snapshot(self) -> SuiteBudgetSnapshot:
        return SuiteBudgetSnapshot(
            policy=self.policy,
            ai_requests_used=self._ai_requests_used,
            browser_runs_used=self._browser_runs_used,
            elapsed_seconds=self.elapsed_seconds(),
            exhausted_reason=self._exhausted_reason,
        )
