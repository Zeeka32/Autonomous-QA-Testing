from dataclasses import FrozenInstanceError

import pytest

from autonomous_qa.plans import ElementVisibleAssertion
from autonomous_qa.suites import (
    MAX_SUITE_TESTS,
    SuiteValidationError,
    TestCase as SuiteCase,
    TestKind as SuiteTestKind,
    TestSuite as SuiteDefinition,
)


def page_load_test(test_id: str = "page-load") -> SuiteCase:
    return SuiteCase(
        test_id=test_id,
        name="Page loads successfully",
        kind=SuiteTestKind.PAGE_LOAD,
    )


def test_accepts_a_suite_with_deterministic_and_browser_cases() -> None:
    suite = SuiteDefinition(
        url="https://example.com",
        request="Check the page and open the account menu",
        tests=(
            page_load_test(),
            SuiteCase(
                test_id="page-title",
                name="Page has a title",
                kind=SuiteTestKind.TITLE_PRESENT,
            ),
            SuiteCase(
                test_id="open-account-menu",
                name="Open the account menu",
                kind=SuiteTestKind.BROWSER_GOAL,
                goal="Open the account menu",
                assertions=(
                    ElementVisibleAssertion(selector="#account-menu"),
                ),
            ),
        ),
    )

    assert suite.tests[2].goal == "Open the account menu"
    assert suite.tests[2].assertions == (
        ElementVisibleAssertion(selector="#account-menu"),
    )


@pytest.mark.parametrize(
    "test_id",
    ["", "   ", "Page Load", "page/load", "-page", "page-"],
)
def test_rejects_invalid_test_case_ids(test_id: str) -> None:
    with pytest.raises(SuiteValidationError, match="test case ID"):
        page_load_test(test_id)


def test_browser_goal_requires_a_goal() -> None:
    with pytest.raises(SuiteValidationError, match="browser goal"):
        SuiteCase(
            test_id="submit-form",
            name="Submit the form",
            kind=SuiteTestKind.BROWSER_GOAL,
        )


@pytest.mark.parametrize(
    "kind",
    [
        SuiteTestKind.PAGE_LOAD,
        SuiteTestKind.TITLE_PRESENT,
        SuiteTestKind.ACCESSIBILITY,
    ],
)
def test_deterministic_cases_reject_browser_goals(kind: SuiteTestKind) -> None:
    with pytest.raises(SuiteValidationError, match="cannot include"):
        SuiteCase(
            test_id="basic-check",
            name="Run a basic check",
            kind=kind,
            goal="Click something",
        )


def test_deterministic_cases_reject_assertions() -> None:
    with pytest.raises(SuiteValidationError, match="cannot include assertions"):
        SuiteCase(
            test_id="page-load",
            name="Page loads successfully",
            kind=SuiteTestKind.PAGE_LOAD,
            assertions=(ElementVisibleAssertion(selector="main"),),
        )


@pytest.mark.parametrize(
    "url",
    ["", "example.com", "ftp://example.com", "not-a-url"],
)
def test_suite_requires_an_absolute_http_url(url: str) -> None:
    with pytest.raises(SuiteValidationError, match="absolute HTTP"):
        SuiteDefinition(url=url, tests=(page_load_test(),))


def test_suite_requires_at_least_one_test() -> None:
    with pytest.raises(SuiteValidationError, match="at least one"):
        SuiteDefinition(url="https://example.com", tests=())


def test_suite_has_a_test_limit() -> None:
    tests = tuple(
        page_load_test(f"page-load-{index}")
        for index in range(MAX_SUITE_TESTS + 1)
    )

    with pytest.raises(SuiteValidationError, match="more than"):
        SuiteDefinition(url="https://example.com", tests=tests)


def test_suite_rejects_duplicate_test_ids() -> None:
    with pytest.raises(SuiteValidationError, match="must be unique"):
        SuiteDefinition(
            url="https://example.com",
            tests=(page_load_test(), page_load_test()),
        )


def test_suite_models_are_immutable() -> None:
    test_case = page_load_test()
    suite = SuiteDefinition(
        url="https://example.com",
        tests=(test_case,),
    )

    with pytest.raises(FrozenInstanceError):
        test_case.name = "Changed"
    with pytest.raises(FrozenInstanceError):
        suite.url = "https://changed.example.com"


def test_case_requires_a_supported_kind() -> None:
    with pytest.raises(SuiteValidationError, match="kind is unsupported"):
        SuiteCase(
            test_id="page-load",
            name="Page loads successfully",
            kind="page_load",
        )


def test_case_assertions_must_be_a_tuple() -> None:
    with pytest.raises(SuiteValidationError, match="must be a tuple"):
        SuiteCase(
            test_id="open-menu",
            name="Open the menu",
            kind=SuiteTestKind.BROWSER_GOAL,
            goal="Open the menu",
            assertions=[],
        )


def test_suite_tests_must_be_a_tuple() -> None:
    with pytest.raises(SuiteValidationError, match="must be a tuple"):
        SuiteDefinition(
            url="https://example.com",
            tests=[page_load_test()],
        )


def test_suite_rejects_a_blank_request() -> None:
    with pytest.raises(SuiteValidationError, match="must not be blank"):
        SuiteDefinition(
            url="https://example.com",
            tests=(page_load_test(),),
            request="   ",
        )
