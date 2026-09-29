from autonomous_qa.checks import (
    check_http_status,
    check_title,
    run_checks,
)
from autonomous_qa.models import CheckResult, PageSnapshot


def test_http_status_passes_below_400() -> None:
    snapshot = PageSnapshot(
        url="https://example.com",
        status=200,
        title="Example Domain",
    )

    result = check_http_status(snapshot)

    assert result == CheckResult(
        name="HTTP status",
        passed=True,
        message="Page returned HTTP 200",
    )


def test_http_status_fails_at_400_or_above() -> None:
    snapshot = PageSnapshot(
        url="https://example.com/missing",
        status=404,
        title="Not Found",
    )

    result = check_http_status(snapshot)

    assert result.passed is False
    assert result.message == "Page returned HTTP 404"


def test_http_status_fails_when_response_is_missing() -> None:
    snapshot = PageSnapshot(
        url="about:blank",
        status=None,
        title="",
    )

    result = check_http_status(snapshot)

    assert result.passed is False
    assert result.message == "Navigation did not return an HTTP response"


def test_title_fails_when_it_contains_only_whitespace() -> None:
    snapshot = PageSnapshot(
        url="https://example.com",
        status=200,
        title="   ",
    )

    result = check_title(snapshot)

    assert result == CheckResult(
        name="Page title",
        passed=False,
        message="Page title is empty",
    )


def test_run_checks_returns_each_check_in_order() -> None:
    snapshot = PageSnapshot(
        url="https://example.com",
        status=200,
        title="Example Domain",
    )

    results = run_checks(snapshot)

    assert [result.name for result in results] == ["HTTP status", "Page title"]
    assert all(result.passed for result in results)


def test_run_checks_appends_optional_url_assertion() -> None:
    assertion_result = CheckResult(
        name="Expected URL",
        passed=True,
        message='Final URL "https://example.com/" contains "example.com"',
    )
    snapshot = PageSnapshot(
        url="https://example.com/",
        status=200,
        title="Example Domain",
        assertion_results=(assertion_result,),
    )

    results = run_checks(snapshot)

    assert [result.name for result in results] == [
        "HTTP status",
        "Page title",
        "Expected URL",
    ]
    assert all(result.passed for result in results)
