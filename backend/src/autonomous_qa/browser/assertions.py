from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from ..models import CheckResult
from ..plans import (
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
    PlanAssertion,
    TitleContainsAssertion,
    UrlContainsAssertion,
)


ASSERTION_TIMEOUT_MS = 10_000


def _contains_result(
    name: str,
    subject_name: str,
    actual: str,
    expected: str,
) -> CheckResult:
    passed = expected in actual
    relationship = "contains" if passed else "does not contain"
    return CheckResult(
        name=name,
        passed=passed,
        message=f'{subject_name} "{actual}" {relationship} "{expected}"',
    )


def _element_state_result(
    page: Page,
    selector: str,
    name: str,
    state_name: str,
    locator_method: str,
    expected: bool,
) -> CheckResult:
    try:
        locator = page.locator(selector)
        actual = getattr(locator, locator_method)()
        passed = actual is expected
        relationship = state_name if passed else f"not {state_name}"
        message = f'Element "{selector}" is {relationship}'
    except PlaywrightError as error:
        passed = False
        error_summary = str(error).splitlines()[0]
        message = f'Could not check element "{selector}": {error_summary}'
    return CheckResult(name=name, passed=passed, message=message)


def evaluate_assertions(
    page: Page,
    assertions: tuple[PlanAssertion, ...],
) -> tuple[CheckResult, ...]:
    results: list[CheckResult] = []

    for assertion in assertions:
        if isinstance(assertion, UrlContainsAssertion):
            results.append(
                _contains_result(
                    "Expected URL",
                    "Final URL",
                    page.url,
                    assertion.value,
                )
            )
        elif isinstance(assertion, TitleContainsAssertion):
            results.append(
                _contains_result(
                    "Expected title",
                    "Page title",
                    page.title(),
                    assertion.value,
                )
            )
        elif isinstance(assertion, ElementVisibleAssertion):
            results.append(
                _element_state_result(
                    page,
                    assertion.selector,
                    "Visible element",
                    "visible",
                    "is_visible",
                    True,
                )
            )
        elif isinstance(assertion, ElementHiddenAssertion):
            results.append(
                _element_state_result(
                    page,
                    assertion.selector,
                    "Hidden element",
                    "hidden",
                    "is_visible",
                    False,
                )
            )
        elif isinstance(assertion, ElementEnabledAssertion):
            results.append(
                _element_state_result(
                    page,
                    assertion.selector,
                    "Enabled element",
                    "enabled",
                    "is_enabled",
                    True,
                )
            )
        elif isinstance(assertion, ElementDisabledAssertion):
            results.append(
                _element_state_result(
                    page,
                    assertion.selector,
                    "Disabled element",
                    "disabled",
                    "is_enabled",
                    False,
                )
            )
        elif isinstance(assertion, ElementCheckedAssertion):
            results.append(
                _element_state_result(
                    page,
                    assertion.selector,
                    "Checked element",
                    "checked",
                    "is_checked",
                    True,
                )
            )
        elif isinstance(assertion, ElementUncheckedAssertion):
            results.append(
                _element_state_result(
                    page,
                    assertion.selector,
                    "Unchecked element",
                    "unchecked",
                    "is_checked",
                    False,
                )
            )
        elif isinstance(assertion, ElementValueEqualsAssertion):
            try:
                actual_value = page.locator(
                    assertion.selector
                ).input_value(timeout=ASSERTION_TIMEOUT_MS)
                passed = actual_value == assertion.value
                relationship = "equals" if passed else "does not equal"
                results.append(
                    CheckResult(
                        name="Expected element value",
                        passed=passed,
                        message=(
                            f'Element "{assertion.selector}" value '
                            f'"{actual_value}" {relationship} '
                            f'"{assertion.value}"'
                        ),
                    )
                )
            except PlaywrightError as error:
                error_summary = str(error).splitlines()[0]
                results.append(
                    CheckResult(
                        name="Expected element value",
                        passed=False,
                        message=(
                            f'Could not read value of element '
                            f'"{assertion.selector}": {error_summary}'
                        ),
                    )
                )
        elif isinstance(assertion, ElementCountEqualsAssertion):
            try:
                actual_count = page.locator(assertion.selector).count()
                results.append(
                    CheckResult(
                        name="Expected element count",
                        passed=actual_count == assertion.count,
                        message=(
                            f'Selector "{assertion.selector}" matched '
                            f"{actual_count} elements; expected "
                            f"{assertion.count}"
                        ),
                    )
                )
            except PlaywrightError as error:
                error_summary = str(error).splitlines()[0]
                results.append(
                    CheckResult(
                        name="Expected element count",
                        passed=False,
                        message=(
                            f'Could not count selector '
                            f'"{assertion.selector}": {error_summary}'
                        ),
                    )
                )
        elif isinstance(assertion, ElementAttributeContainsAssertion):
            try:
                actual_attribute = page.locator(
                    assertion.selector
                ).get_attribute(
                    assertion.attribute,
                    timeout=ASSERTION_TIMEOUT_MS,
                )
                if actual_attribute is None:
                    results.append(
                        CheckResult(
                            name="Expected element attribute",
                            passed=False,
                            message=(
                                f'Element "{assertion.selector}" has no '
                                f'attribute "{assertion.attribute}"'
                            ),
                        )
                    )
                else:
                    results.append(
                        _contains_result(
                            "Expected element attribute",
                            (
                                f'Element "{assertion.selector}" attribute '
                                f'"{assertion.attribute}"'
                            ),
                            actual_attribute,
                            assertion.value,
                        )
                    )
            except PlaywrightError as error:
                error_summary = str(error).splitlines()[0]
                results.append(
                    CheckResult(
                        name="Expected element attribute",
                        passed=False,
                        message=(
                            f'Could not read attribute '
                            f'"{assertion.attribute}" from element '
                            f'"{assertion.selector}": {error_summary}'
                        ),
                    )
                )
        elif isinstance(assertion, ElementTextContainsAssertion):
            try:
                actual_text = page.locator(assertion.selector).inner_text(
                    timeout=ASSERTION_TIMEOUT_MS
                )
                results.append(
                    _contains_result(
                        "Expected element text",
                        f'Element "{assertion.selector}" text',
                        actual_text,
                        assertion.value,
                    )
                )
            except PlaywrightError as error:
                error_summary = str(error).splitlines()[0]
                results.append(
                    CheckResult(
                        name="Expected element text",
                        passed=False,
                        message=(
                            f'Could not read element "{assertion.selector}": '
                            f"{error_summary}"
                        ),
                    )
                )

    return tuple(results)
