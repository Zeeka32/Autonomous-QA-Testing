from dataclasses import dataclass
from typing import Literal


ActionStatus = Literal["passed", "failed", "skipped"]


@dataclass(frozen=True)
class InteractiveElement:
    selector: str
    tag: str
    role: str | None
    label: str
    input_type: str | None
    disabled: bool
    href: str | None
    options: tuple[str, ...] = ()
    checked: bool | None = None


@dataclass(frozen=True)
class PageObservation:
    elements: tuple[InteractiveElement, ...]
    truncated: bool


@dataclass(frozen=True)
class ActionResult:
    step_number: int
    kind: str
    status: ActionStatus
    duration_ms: float
    url_before: str
    url_after: str
    message: str

    @property
    def passed(self) -> bool:
        return self.status == "passed"


@dataclass(frozen=True)
class PageSnapshot:
    url: str
    status: int | None
    title: str
    observation: PageObservation | None = None
    action_results: tuple[ActionResult, ...] = ()
    assertion_results: tuple["CheckResult", ...] = ()


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    message: str
