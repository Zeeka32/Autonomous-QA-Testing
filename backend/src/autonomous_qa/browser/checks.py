from ..models import CheckResult, PageSnapshot


def check_http_status(snapshot: PageSnapshot) -> CheckResult:
    if snapshot.status is None:
        return CheckResult(
            name="HTTP status",
            passed=False,
            message="Navigation did not return an HTTP response",
        )

    passed = snapshot.status < 400
    return CheckResult(
        name="HTTP status",
        passed=passed,
        message=f"Page returned HTTP {snapshot.status}",
    )


def check_title(snapshot: PageSnapshot) -> CheckResult:
    title = snapshot.title.strip()
    passed = bool(title)
    message = f'Page title is "{title}"' if passed else "Page title is empty"
    return CheckResult(name="Page title", passed=passed, message=message)


def run_checks(snapshot: PageSnapshot) -> list[CheckResult]:
    results = [
        check_http_status(snapshot),
        check_title(snapshot),
    ]
    results.extend(snapshot.assertion_results)
    return results
