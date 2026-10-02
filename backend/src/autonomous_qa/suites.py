import re
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlparse

from .models import CheckResult
from .plans import (
    ALLOWED_ASSERTION_TYPES,
    MAX_PLAN_ASSERTIONS,
    PlanAssertion,
)


MAX_SUITE_TESTS = 20
MAX_TEST_ID_LENGTH = 64
MAX_TEST_NAME_LENGTH = 120
MAX_TEST_GOAL_LENGTH = 1_000
MAX_SUITE_REQUEST_LENGTH = 2_000
MAX_RESULT_MESSAGE_LENGTH = 2_000
TEST_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")


class SuiteValidationError(ValueError):
    """Raised when a test case or test suite is invalid."""


class TestKind(StrEnum):
    PAGE_LOAD = "page_load"
    TITLE_PRESENT = "title_present"
    ACCESSIBILITY = "accessibility"
    BROWSER_GOAL = "browser_goal"


def _require_bounded_text(
    value: str,
    field_name: str,
    maximum_length: int,
) -> None:
    if not isinstance(value, str):
        raise SuiteValidationError(f"{field_name} must be a string")
    if not value.strip():
        raise SuiteValidationError(f"{field_name} must not be blank")
    if len(value) > maximum_length:
        raise SuiteValidationError(
            f"{field_name} cannot exceed {maximum_length} characters"
        )


@dataclass(frozen=True)
class TestCase:
    test_id: str
    name: str
    kind: TestKind
    goal: str | None = None
    assertions: tuple[PlanAssertion, ...] = ()

    def __post_init__(self) -> None:
        _require_bounded_text(
            self.test_id,
            "test case ID",
            MAX_TEST_ID_LENGTH,
        )
        if TEST_ID_PATTERN.fullmatch(self.test_id) is None:
            raise SuiteValidationError(
                "test case ID must use lowercase letters, numbers, "
                "hyphens, or underscores"
            )
        _require_bounded_text(
            self.name,
            "test case name",
            MAX_TEST_NAME_LENGTH,
        )
        if not isinstance(self.kind, TestKind):
            raise SuiteValidationError("test case kind is unsupported")
        if not isinstance(self.assertions, tuple):
            raise SuiteValidationError(
                "test case assertions must be a tuple"
            )
        if len(self.assertions) > MAX_PLAN_ASSERTIONS:
            raise SuiteValidationError(
                "test case cannot contain more than "
                f"{MAX_PLAN_ASSERTIONS} assertions"
            )
        if not all(
            isinstance(assertion, ALLOWED_ASSERTION_TYPES)
            for assertion in self.assertions
        ):
            raise SuiteValidationError(
                "test case contains an unsupported assertion"
            )

        if self.kind is TestKind.BROWSER_GOAL:
            _require_bounded_text(
                self.goal,
                "browser goal",
                MAX_TEST_GOAL_LENGTH,
            )
            return

        if self.goal is not None:
            raise SuiteValidationError(
                "deterministic test cases cannot include a browser goal"
            )
        if self.assertions:
            raise SuiteValidationError(
                "deterministic test cases cannot include assertions"
            )


@dataclass(frozen=True)
class TestSuite:
    url: str
    tests: tuple[TestCase, ...]
    request: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.url, str):
            raise SuiteValidationError("test suite URL must be a string")
        parsed_url = urlparse(self.url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise SuiteValidationError(
                "test suite URL must be an absolute HTTP or HTTPS URL"
            )
        if not isinstance(self.tests, tuple):
            raise SuiteValidationError("test suite tests must be a tuple")
        if not self.tests:
            raise SuiteValidationError(
                "test suite must contain at least one test case"
            )
        if len(self.tests) > MAX_SUITE_TESTS:
            raise SuiteValidationError(
                f"test suite cannot contain more than {MAX_SUITE_TESTS} tests"
            )
        if not all(isinstance(test, TestCase) for test in self.tests):
            raise SuiteValidationError(
                "test suite contains an unsupported test case"
            )
        test_ids = [test.test_id for test in self.tests]
        if len(test_ids) != len(set(test_ids)):
            raise SuiteValidationError(
                "test suite test case IDs must be unique"
            )
        if self.request is not None:
            _require_bounded_text(
                self.request,
                "test suite request",
                MAX_SUITE_REQUEST_LENGTH,
            )


class TestStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class TestOutcome:
    status: TestStatus
    message: str
    checks: tuple[CheckResult, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.status, TestStatus):
            raise SuiteValidationError("test outcome status is unsupported")
        _require_bounded_text(
            self.message,
            "test outcome message",
            MAX_RESULT_MESSAGE_LENGTH,
        )
        if not isinstance(self.checks, tuple):
            raise SuiteValidationError("test outcome checks must be a tuple")
        if not all(isinstance(check, CheckResult) for check in self.checks):
            raise SuiteValidationError(
                "test outcome contains an unsupported check result"
            )
        if (
            self.status is TestStatus.PASSED
            and any(not check.passed for check in self.checks)
        ):
            raise SuiteValidationError(
                "passed test outcomes cannot contain failed checks"
            )


@dataclass(frozen=True)
class TestCaseResult:
    test_id: str
    kind: TestKind
    status: TestStatus
    duration_ms: float
    message: str
    checks: tuple[CheckResult, ...] = ()

    def __post_init__(self) -> None:
        _require_bounded_text(
            self.test_id,
            "test result ID",
            MAX_TEST_ID_LENGTH,
        )
        if not isinstance(self.kind, TestKind):
            raise SuiteValidationError("test result kind is unsupported")
        if not isinstance(self.status, TestStatus):
            raise SuiteValidationError("test result status is unsupported")
        if (
            not isinstance(self.duration_ms, (int, float))
            or isinstance(self.duration_ms, bool)
            or self.duration_ms < 0
        ):
            raise SuiteValidationError(
                "test result duration must be a non-negative number"
            )
        _require_bounded_text(
            self.message,
            "test result message",
            MAX_RESULT_MESSAGE_LENGTH,
        )
        if not isinstance(self.checks, tuple):
            raise SuiteValidationError("test result checks must be a tuple")
        if not all(isinstance(check, CheckResult) for check in self.checks):
            raise SuiteValidationError(
                "test result contains an unsupported check result"
            )
        if (
            self.status is TestStatus.PASSED
            and any(not check.passed for check in self.checks)
        ):
            raise SuiteValidationError(
                "passed test results cannot contain failed checks"
            )

    @property
    def passed(self) -> bool:
        return self.status is TestStatus.PASSED


@dataclass(frozen=True)
class SuiteRunResult:
    suite: TestSuite
    results: tuple[TestCaseResult, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.suite, TestSuite):
            raise SuiteValidationError(
                "suite run result must reference a test suite"
            )
        if not isinstance(self.results, tuple):
            raise SuiteValidationError(
                "suite run results must be a tuple"
            )
        if not all(
            isinstance(result, TestCaseResult)
            for result in self.results
        ):
            raise SuiteValidationError(
                "suite run contains an unsupported test result"
            )
        expected_ids = tuple(test.test_id for test in self.suite.tests)
        actual_ids = tuple(result.test_id for result in self.results)
        if actual_ids != expected_ids:
            raise SuiteValidationError(
                "suite run results must match suite test order and IDs"
            )

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)
