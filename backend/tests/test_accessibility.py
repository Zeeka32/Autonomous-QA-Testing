import pytest

from autonomous_qa.accessibility import (
    AccessibilityAuditError,
    audit_accessibility,
)


class FakePage:
    def __init__(self, result) -> None:
        self.result = result
        self.script = None

    def evaluate(self, script):
        self.script = script
        return self.result


def test_audit_accessibility_converts_browser_results() -> None:
    page = FakePage(
        [
            {
                "name": "Document language",
                "passed": True,
                "message": 'Document language is "en"',
            },
            {
                "name": "Form control names",
                "passed": False,
                "message": (
                    "1 visible form controls are missing accessible names: "
                    "input#email"
                ),
            },
        ]
    )

    results = audit_accessibility(page)

    assert page.script
    assert [result.name for result in results] == [
        "Document language",
        "Form control names",
    ]
    assert [result.passed for result in results] == [True, False]
    assert "input#email" in results[1].message


@pytest.mark.parametrize(
    "result",
    [
        None,
        [],
        ["invalid"],
        [{"name": "", "passed": True, "message": "ok"}],
        [{"name": "Check", "passed": "yes", "message": "ok"}],
        [{"name": "Check", "passed": True, "message": ""}],
    ],
)
def test_audit_accessibility_rejects_invalid_results(result) -> None:
    with pytest.raises(AccessibilityAuditError, match="invalid|any checks"):
        audit_accessibility(FakePage(result))


def test_audit_accessibility_bounds_messages() -> None:
    page = FakePage(
        [
            {
                "name": "Form control names",
                "passed": False,
                "message": "x" * 3_000,
            }
        ]
    )

    result = audit_accessibility(page)

    assert len(result[0].message) == 2_000
