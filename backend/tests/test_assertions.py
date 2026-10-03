from playwright.sync_api import Error as PlaywrightError

import pytest

from autonomous_qa.browser.assertions import evaluate_assertions
from autonomous_qa.models import CheckResult
from autonomous_qa.plans import (
    ElementAttributeContainsAssertion,
    ElementCheckedAssertion,
    ElementCountEqualsAssertion,
    ElementDisabledAssertion,
    ElementEnabledAssertion,
    ElementHiddenAssertion,
    ElementTextContainsAssertion,
    ElementUncheckedAssertion,
    ElementValueEqualsAssertion,
    ElementVisibleAssertion,
    TitleContainsAssertion,
    UrlContainsAssertion,
)


class FakeLocator:
    def __init__(
        self,
        visible: bool,
        text: str,
        error: PlaywrightError | None = None,
        enabled: bool = True,
        checked: bool = False,
        value: str = "",
        matched_count: int = 1,
        attributes: dict[str, str] | None = None,
    ) -> None:
        self.visible = visible
        self.text = text
        self.error = error
        self.enabled = enabled
        self.checked = checked
        self.value = value
        self.matched_count = matched_count
        self.attributes = attributes or {}

    def is_visible(self) -> bool:
        if self.error is not None:
            raise self.error
        return self.visible

    def is_enabled(self) -> bool:
        if self.error is not None:
            raise self.error
        return self.enabled

    def is_checked(self) -> bool:
        if self.error is not None:
            raise self.error
        return self.checked

    def input_value(self, timeout: int) -> str:
        if self.error is not None:
            raise self.error
        assert timeout == 10_000
        return self.value

    def count(self) -> int:
        if self.error is not None:
            raise self.error
        return self.matched_count

    def get_attribute(self, name: str, timeout: int) -> str | None:
        if self.error is not None:
            raise self.error
        assert timeout == 10_000
        return self.attributes.get(name)

    def inner_text(self, timeout: int) -> str:
        if self.error is not None:
            raise self.error
        assert timeout == 10_000
        return self.text


class FakePage:
    def __init__(
        self,
        *,
        url: str = "https://example.com/dashboard",
        title: str = "Account dashboard",
        visible: bool = True,
        enabled: bool = True,
        checked: bool = False,
        value: str = "",
        matched_count: int = 1,
        attributes: dict[str, str] | None = None,
        text: str = "Welcome back, Ada",
        locator_error: PlaywrightError | None = None,
    ) -> None:
        self.url = url
        self._title = title
        self.visible = visible
        self.enabled = enabled
        self.checked = checked
        self.value = value
        self.matched_count = matched_count
        self.attributes = attributes
        self.text = text
        self.locator_error = locator_error
        self.requested_selectors: list[str] = []

    def title(self) -> str:
        return self._title

    def locator(self, selector: str) -> FakeLocator:
        self.requested_selectors.append(selector)
        return FakeLocator(
            self.visible,
            self.text,
            self.locator_error,
            enabled=self.enabled,
            checked=self.checked,
            value=self.value,
            matched_count=self.matched_count,
            attributes=self.attributes,
        )


def test_evaluates_url_and_title_assertions() -> None:
    page = FakePage()

    results = evaluate_assertions(
        page,
        (
            UrlContainsAssertion(value="/dashboard"),
            TitleContainsAssertion(value="dashboard"),
        ),
    )

    assert results == (
        CheckResult(
            name="Expected URL",
            passed=True,
            message=(
                'Final URL "https://example.com/dashboard" '
                'contains "/dashboard"'
            ),
        ),
        CheckResult(
            name="Expected title",
            passed=True,
            message='Page title "Account dashboard" contains "dashboard"',
        ),
    )


def test_element_visible_assertion_passes_for_a_visible_element() -> None:
    page = FakePage(visible=True)

    results = evaluate_assertions(
        page,
        (ElementVisibleAssertion(selector="#welcome"),),
    )

    assert results == (
        CheckResult(
            name="Visible element",
            passed=True,
            message='Element "#welcome" is visible',
        ),
    )
    assert page.requested_selectors == ["#welcome"]


def test_element_visible_assertion_fails_for_a_hidden_element() -> None:
    page = FakePage(visible=False)

    result = evaluate_assertions(
        page,
        (ElementVisibleAssertion(selector="#welcome"),),
    )[0]

    assert result.passed is False
    assert result.message == 'Element "#welcome" is not visible'


def test_element_visible_assertion_reports_selector_errors() -> None:
    page = FakePage(locator_error=PlaywrightError("invalid selector\ncall log"))

    result = evaluate_assertions(
        page,
        (ElementVisibleAssertion(selector="[invalid"),),
    )[0]

    assert result.passed is False
    assert result.message == (
        'Could not check element "[invalid": invalid selector'
    )


@pytest.mark.parametrize(
    ("assertion", "page", "name", "state"),
    [
        (
            ElementHiddenAssertion(selector="#target"),
            FakePage(visible=False),
            "Hidden element",
            "hidden",
        ),
        (
            ElementEnabledAssertion(selector="#target"),
            FakePage(enabled=True),
            "Enabled element",
            "enabled",
        ),
        (
            ElementDisabledAssertion(selector="#target"),
            FakePage(enabled=False),
            "Disabled element",
            "disabled",
        ),
        (
            ElementCheckedAssertion(selector="#target"),
            FakePage(checked=True),
            "Checked element",
            "checked",
        ),
        (
            ElementUncheckedAssertion(selector="#target"),
            FakePage(checked=False),
            "Unchecked element",
            "unchecked",
        ),
    ],
)
def test_element_state_assertions_pass(
    assertion,
    page,
    name,
    state,
) -> None:
    result = evaluate_assertions(page, (assertion,))[0]

    assert result == CheckResult(
        name=name,
        passed=True,
        message=f'Element "#target" is {state}',
    )


@pytest.mark.parametrize(
    "assertion",
    [
        ElementHiddenAssertion(selector="#target"),
        ElementDisabledAssertion(selector="#target"),
        ElementCheckedAssertion(selector="#target"),
    ],
)
def test_element_state_assertions_report_failed_expectations(
    assertion,
) -> None:
    result = evaluate_assertions(FakePage(), (assertion,))[0]

    assert result.passed is False
    assert " is not " in result.message


def test_general_element_assertions_pass() -> None:
    page = FakePage(
        value="Ada",
        matched_count=2,
        attributes={"class": "status complete"},
    )

    results = evaluate_assertions(
        page,
        (
            ElementValueEqualsAssertion(
                selector="#name",
                value="Ada",
            ),
            ElementCountEqualsAssertion(selector=".result", count=2),
            ElementAttributeContainsAssertion(
                selector="#status",
                attribute="class",
                value="complete",
            ),
        ),
    )

    assert results == (
        CheckResult(
            name="Expected element value",
            passed=True,
            message='Element "#name" value "Ada" equals "Ada"',
        ),
        CheckResult(
            name="Expected element count",
            passed=True,
            message='Selector ".result" matched 2 elements; expected 2',
        ),
        CheckResult(
            name="Expected element attribute",
            passed=True,
            message=(
                'Element "#status" attribute "class" '
                '"status complete" contains "complete"'
            ),
        ),
    )


def test_element_attribute_assertion_fails_when_attribute_is_missing() -> None:
    result = evaluate_assertions(
        FakePage(),
        (
            ElementAttributeContainsAssertion(
                selector="#status",
                attribute="aria-current",
                value="page",
            ),
        ),
    )[0]

    assert result.passed is False
    assert result.message == (
        'Element "#status" has no attribute "aria-current"'
    )


def test_element_text_assertion_checks_the_rendered_text() -> None:
    page = FakePage(text="Submission complete for Ada")

    result = evaluate_assertions(
        page,
        (
            ElementTextContainsAssertion(
                selector="#result",
                value="complete",
            ),
        ),
    )[0]

    assert result == CheckResult(
        name="Expected element text",
        passed=True,
        message=(
            'Element "#result" text "Submission complete for Ada" '
            'contains "complete"'
        ),
    )


def test_element_text_assertion_reports_selector_errors() -> None:
    page = FakePage(locator_error=PlaywrightError("invalid selector\ncall log"))

    result = evaluate_assertions(
        page,
        (
            ElementTextContainsAssertion(
                selector="[invalid",
                value="complete",
            ),
        ),
    )[0]

    assert result.passed is False
    assert result.message == (
        'Could not read element "[invalid": invalid selector'
    )
