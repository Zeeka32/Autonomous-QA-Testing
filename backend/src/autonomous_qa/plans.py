from dataclasses import dataclass, field
from enum import StrEnum
from urllib.parse import urlparse


MAX_PLAN_ACTIONS = 20
MAX_PLAN_ASSERTIONS = 20
ALLOWED_PRESS_KEYS = frozenset(
    {"Enter", "Escape", "Tab", "ArrowUp", "ArrowDown"}
)


class PlanValidationError(ValueError):
    """Raised when an action plan is invalid or unsafe to execute."""


class ActionKind(StrEnum):
    NAVIGATE = "navigate"
    CLICK = "click"
    FILL = "fill"
    WAIT_FOR = "wait_for"
    SELECT = "select"
    CHECK = "check"
    UNCHECK = "uncheck"
    PRESS = "press"


class AssertionKind(StrEnum):
    URL_CONTAINS = "url_contains"
    TITLE_CONTAINS = "title_contains"
    ELEMENT_VISIBLE = "element_visible"
    ELEMENT_HIDDEN = "element_hidden"
    ELEMENT_ENABLED = "element_enabled"
    ELEMENT_DISABLED = "element_disabled"
    ELEMENT_CHECKED = "element_checked"
    ELEMENT_UNCHECKED = "element_unchecked"
    ELEMENT_VALUE_EQUALS = "element_value_equals"
    ELEMENT_COUNT_EQUALS = "element_count_equals"
    ELEMENT_ATTRIBUTE_CONTAINS = "element_attribute_contains"
    ELEMENT_TEXT_CONTAINS = "element_text_contains"


class CriteriaSource(StrEnum):
    USER_PROVIDED = "user_provided"
    AI_GENERATED = "ai_generated"
    NONE = "none"


def _require_nonblank(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise PlanValidationError(f"{field_name} must be a string")
    if not value.strip():
        raise PlanValidationError(f"{field_name} must not be blank")


@dataclass(frozen=True)
class NavigateAction:
    url: str
    kind: ActionKind = field(init=False, default=ActionKind.NAVIGATE)

    def __post_init__(self) -> None:
        if not isinstance(self.url, str):
            raise PlanValidationError("navigate URL must be a string")
        parsed_url = urlparse(self.url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise PlanValidationError(
                "navigate URL must be an absolute HTTP or HTTPS URL"
            )


@dataclass(frozen=True)
class ClickAction:
    selector: str
    kind: ActionKind = field(init=False, default=ActionKind.CLICK)

    def __post_init__(self) -> None:
        _require_nonblank(self.selector, "click selector")


@dataclass(frozen=True)
class FillAction:
    selector: str
    value: str
    kind: ActionKind = field(init=False, default=ActionKind.FILL)

    def __post_init__(self) -> None:
        _require_nonblank(self.selector, "fill selector")
        if not isinstance(self.value, str):
            raise PlanValidationError("fill value must be a string")


@dataclass(frozen=True)
class WaitForAction:
    selector: str
    kind: ActionKind = field(init=False, default=ActionKind.WAIT_FOR)

    def __post_init__(self) -> None:
        _require_nonblank(self.selector, "wait selector")


@dataclass(frozen=True)
class SelectAction:
    selector: str
    value: str
    kind: ActionKind = field(init=False, default=ActionKind.SELECT)

    def __post_init__(self) -> None:
        _require_nonblank(self.selector, "select selector")
        if not isinstance(self.value, str):
            raise PlanValidationError("select value must be a string")


@dataclass(frozen=True)
class CheckAction:
    selector: str
    kind: ActionKind = field(init=False, default=ActionKind.CHECK)

    def __post_init__(self) -> None:
        _require_nonblank(self.selector, "check selector")


@dataclass(frozen=True)
class UncheckAction:
    selector: str
    kind: ActionKind = field(init=False, default=ActionKind.UNCHECK)

    def __post_init__(self) -> None:
        _require_nonblank(self.selector, "uncheck selector")


@dataclass(frozen=True)
class PressAction:
    selector: str
    key: str
    kind: ActionKind = field(init=False, default=ActionKind.PRESS)

    def __post_init__(self) -> None:
        _require_nonblank(self.selector, "press selector")
        if not isinstance(self.key, str):
            raise PlanValidationError("press key must be a string")
        if self.key not in ALLOWED_PRESS_KEYS:
            allowed = ", ".join(sorted(ALLOWED_PRESS_KEYS))
            raise PlanValidationError(
                f'press key must be one of: {allowed}; received "{self.key}"'
            )


@dataclass(frozen=True)
class UrlContainsAssertion:
    value: str
    kind: AssertionKind = field(init=False, default=AssertionKind.URL_CONTAINS)

    def __post_init__(self) -> None:
        _require_nonblank(self.value, "URL assertion value")


@dataclass(frozen=True)
class TitleContainsAssertion:
    value: str
    kind: AssertionKind = field(
        init=False,
        default=AssertionKind.TITLE_CONTAINS,
    )

    def __post_init__(self) -> None:
        _require_nonblank(self.value, "title assertion value")


@dataclass(frozen=True)
class ElementVisibleAssertion:
    selector: str
    kind: AssertionKind = field(
        init=False,
        default=AssertionKind.ELEMENT_VISIBLE,
    )

    def __post_init__(self) -> None:
        _require_nonblank(self.selector, "element assertion selector")


@dataclass(frozen=True)
class ElementHiddenAssertion:
    selector: str
    kind: AssertionKind = field(
        init=False,
        default=AssertionKind.ELEMENT_HIDDEN,
    )

    def __post_init__(self) -> None:
        _require_nonblank(self.selector, "element assertion selector")


@dataclass(frozen=True)
class ElementEnabledAssertion:
    selector: str
    kind: AssertionKind = field(
        init=False,
        default=AssertionKind.ELEMENT_ENABLED,
    )

    def __post_init__(self) -> None:
        _require_nonblank(self.selector, "element assertion selector")


@dataclass(frozen=True)
class ElementDisabledAssertion:
    selector: str
    kind: AssertionKind = field(
        init=False,
        default=AssertionKind.ELEMENT_DISABLED,
    )

    def __post_init__(self) -> None:
        _require_nonblank(self.selector, "element assertion selector")


@dataclass(frozen=True)
class ElementCheckedAssertion:
    selector: str
    kind: AssertionKind = field(
        init=False,
        default=AssertionKind.ELEMENT_CHECKED,
    )

    def __post_init__(self) -> None:
        _require_nonblank(self.selector, "element assertion selector")


@dataclass(frozen=True)
class ElementUncheckedAssertion:
    selector: str
    kind: AssertionKind = field(
        init=False,
        default=AssertionKind.ELEMENT_UNCHECKED,
    )

    def __post_init__(self) -> None:
        _require_nonblank(self.selector, "element assertion selector")


@dataclass(frozen=True)
class ElementValueEqualsAssertion:
    selector: str
    value: str
    kind: AssertionKind = field(
        init=False,
        default=AssertionKind.ELEMENT_VALUE_EQUALS,
    )

    def __post_init__(self) -> None:
        _require_nonblank(self.selector, "element value assertion selector")
        if not isinstance(self.value, str):
            raise PlanValidationError(
                "element value assertion value must be a string"
            )


@dataclass(frozen=True)
class ElementCountEqualsAssertion:
    selector: str
    count: int
    kind: AssertionKind = field(
        init=False,
        default=AssertionKind.ELEMENT_COUNT_EQUALS,
    )

    def __post_init__(self) -> None:
        _require_nonblank(self.selector, "element count assertion selector")
        if (
            not isinstance(self.count, int)
            or isinstance(self.count, bool)
            or self.count < 0
        ):
            raise PlanValidationError(
                "element count assertion count must be a non-negative integer"
            )


@dataclass(frozen=True)
class ElementAttributeContainsAssertion:
    selector: str
    attribute: str
    value: str
    kind: AssertionKind = field(
        init=False,
        default=AssertionKind.ELEMENT_ATTRIBUTE_CONTAINS,
    )

    def __post_init__(self) -> None:
        _require_nonblank(
            self.selector,
            "element attribute assertion selector",
        )
        _require_nonblank(
            self.attribute,
            "element attribute assertion attribute",
        )
        _require_nonblank(
            self.value,
            "element attribute assertion value",
        )


@dataclass(frozen=True)
class ElementTextContainsAssertion:
    selector: str
    value: str
    kind: AssertionKind = field(
        init=False,
        default=AssertionKind.ELEMENT_TEXT_CONTAINS,
    )

    def __post_init__(self) -> None:
        _require_nonblank(self.selector, "element text assertion selector")
        _require_nonblank(self.value, "element text assertion value")


BrowserAction = (
    NavigateAction
    | ClickAction
    | FillAction
    | WaitForAction
    | SelectAction
    | CheckAction
    | UncheckAction
    | PressAction
)
AgentAction = (
    ClickAction
    | FillAction
    | WaitForAction
    | SelectAction
    | CheckAction
    | UncheckAction
    | PressAction
)
ALLOWED_ACTION_TYPES = (
    NavigateAction,
    ClickAction,
    FillAction,
    WaitForAction,
    SelectAction,
    CheckAction,
    UncheckAction,
    PressAction,
)
PlanAssertion = (
    UrlContainsAssertion
    | TitleContainsAssertion
    | ElementVisibleAssertion
    | ElementHiddenAssertion
    | ElementEnabledAssertion
    | ElementDisabledAssertion
    | ElementCheckedAssertion
    | ElementUncheckedAssertion
    | ElementValueEqualsAssertion
    | ElementCountEqualsAssertion
    | ElementAttributeContainsAssertion
    | ElementTextContainsAssertion
)
ALLOWED_ASSERTION_TYPES = (
    UrlContainsAssertion,
    TitleContainsAssertion,
    ElementVisibleAssertion,
    ElementHiddenAssertion,
    ElementEnabledAssertion,
    ElementDisabledAssertion,
    ElementCheckedAssertion,
    ElementUncheckedAssertion,
    ElementValueEqualsAssertion,
    ElementCountEqualsAssertion,
    ElementAttributeContainsAssertion,
    ElementTextContainsAssertion,
)


@dataclass(frozen=True)
class CompletionCriteria:
    assertions: tuple[PlanAssertion, ...]
    source: CriteriaSource
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.assertions, tuple):
            raise PlanValidationError(
                "completion criteria assertions must be a tuple"
            )
        if not all(
            isinstance(assertion, ALLOWED_ASSERTION_TYPES)
            for assertion in self.assertions
        ):
            raise PlanValidationError(
                "completion criteria contain an unsupported assertion"
            )
        if self.source is CriteriaSource.NONE and self.assertions:
            raise PlanValidationError(
                "criteria source none cannot contain assertions"
            )
        if self.source is not CriteriaSource.NONE and not self.assertions:
            raise PlanValidationError(
                "completion criteria must contain at least one assertion"
            )
        _require_nonblank(self.reason, "completion criteria reason")


@dataclass(frozen=True)
class ActionPlan:
    actions: tuple[BrowserAction, ...]
    assertions: tuple[PlanAssertion, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.actions, tuple):
            raise PlanValidationError("plan actions must be a tuple")
        if not isinstance(self.assertions, tuple):
            raise PlanValidationError("plan assertions must be a tuple")
        if not self.actions:
            raise PlanValidationError("plan must contain at least one action")
        if len(self.actions) > MAX_PLAN_ACTIONS:
            raise PlanValidationError(
                f"plan cannot contain more than {MAX_PLAN_ACTIONS} actions"
            )
        if not all(
            isinstance(action, ALLOWED_ACTION_TYPES)
            for action in self.actions
        ):
            raise PlanValidationError("plan contains an unsupported action")
        if not isinstance(self.actions[0], NavigateAction):
            raise PlanValidationError("plan must begin with a navigate action")
        if len(self.assertions) > MAX_PLAN_ASSERTIONS:
            raise PlanValidationError(
                f"plan cannot contain more than {MAX_PLAN_ASSERTIONS} assertions"
            )
        if not all(
            isinstance(assertion, ALLOWED_ASSERTION_TYPES)
            for assertion in self.assertions
        ):
            raise PlanValidationError("plan contains an unsupported assertion")
