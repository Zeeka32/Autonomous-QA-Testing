from playwright.sync_api import Page

from ..models import CheckResult


MAX_AUDIT_MESSAGE_LENGTH = 2_000


class AccessibilityAuditError(RuntimeError):
    """Raised when a page returns an invalid accessibility audit result."""


ACCESSIBILITY_AUDIT_SCRIPT = r"""
() => {
  const normalize = (value) => (value || "").replace(/\s+/g, " ").trim();
  const visible = (element) => {
    if (element.hidden || element.getAttribute("aria-hidden") === "true") {
      return false;
    }
    const style = window.getComputedStyle(element);
    return style.display !== "none" && style.visibility !== "hidden";
  };
  const describe = (element) => {
    const tag = element.tagName.toLowerCase();
    const id = normalize(element.id);
    const label = normalize(
      element.getAttribute("aria-label") ||
      element.getAttribute("name") ||
      element.getAttribute("src")
    );
    if (id) return `${tag}#${id}`.slice(0, 120);
    if (label) return `${tag}[${label}]`.slice(0, 120);
    return tag;
  };
  const examples = (elements) =>
    elements.slice(0, 5).map(describe).join(", ");
  const accessibleName = (element) => {
    const ariaLabel = normalize(element.getAttribute("aria-label"));
    if (ariaLabel) return ariaLabel;

    const labelledBy = normalize(element.getAttribute("aria-labelledby"));
    if (labelledBy) {
      const referencedText = normalize(
        labelledBy
          .split(/\s+/)
          .map((id) => document.getElementById(id)?.textContent || "")
          .join(" ")
      );
      if (referencedText) return referencedText;
    }

    const labelText = normalize(
      Array.from(element.labels || [])
        .map((label) => label.textContent || "")
        .join(" ")
    );
    if (labelText) return labelText;

    const alt = normalize(element.getAttribute("alt"));
    if (alt) return alt;

    const text = normalize(element.textContent);
    if (text) return text;

    const title = normalize(element.getAttribute("title"));
    if (title) return title;

    const type = normalize(element.getAttribute("type")).toLowerCase();
    if (["button", "submit", "reset"].includes(type)) {
      return normalize(element.getAttribute("value"));
    }
    return "";
  };
  const result = (
    name,
    failures,
    passingMessage,
    failingDescription
  ) => ({
    name,
    passed: failures.length === 0,
    message: failures.length === 0
      ? passingMessage
      : `${failures.length} ${failingDescription}: ${examples(failures)}`,
  });

  const language = normalize(
    document.documentElement.getAttribute("lang")
  );
  const title = normalize(document.title);
  const visibleImages = Array.from(document.querySelectorAll("img"))
    .filter(visible);
  const imagesWithoutAlt = visibleImages.filter(
    (image) => !image.hasAttribute("alt")
  );
  const controls = Array.from(
    document.querySelectorAll(
      'input:not([type="hidden"]), select, textarea'
    )
  ).filter(visible);
  const unnamedControls = controls.filter(
    (control) => !accessibleName(control)
  );
  const interactiveElements = Array.from(
    document.querySelectorAll(
      'button, a[href], [role="button"], [role="link"]'
    )
  ).filter(visible);
  const unnamedInteractiveElements = interactiveElements.filter(
    (element) => !accessibleName(element)
  );
  const frames = Array.from(document.querySelectorAll("iframe"))
    .filter(visible);
  const untitledFrames = frames.filter(
    (frame) => !normalize(frame.getAttribute("title"))
  );

  return [
    {
      name: "Document language",
      passed: Boolean(language),
      message: language
        ? `Document language is "${language}"`
        : "Document is missing a non-empty html lang attribute",
    },
    {
      name: "Document title",
      passed: Boolean(title),
      message: title
        ? `Document title is "${title}"`
        : "Document title is empty",
    },
    result(
      "Image alternative text",
      imagesWithoutAlt,
      "Every visible image has an alt attribute",
      "visible images are missing alt attributes"
    ),
    result(
      "Form control names",
      unnamedControls,
      "Every visible form control has an accessible name",
      "visible form controls are missing accessible names"
    ),
    result(
      "Interactive element names",
      unnamedInteractiveElements,
      "Every visible button and link has an accessible name",
      "visible buttons or links are missing accessible names"
    ),
    result(
      "Frame titles",
      untitledFrames,
      "Every visible iframe has a title",
      "visible iframes are missing titles"
    ),
  ];
}
"""


def audit_accessibility(page: Page) -> tuple[CheckResult, ...]:
    raw_results = page.evaluate(ACCESSIBILITY_AUDIT_SCRIPT)
    if not isinstance(raw_results, list) or not raw_results:
        raise AccessibilityAuditError(
            "Accessibility audit did not return any checks"
        )

    results = []
    for raw_result in raw_results:
        if not isinstance(raw_result, dict):
            raise AccessibilityAuditError(
                "Accessibility audit returned an invalid check"
            )
        name = raw_result.get("name")
        passed = raw_result.get("passed")
        message = raw_result.get("message")
        if (
            not isinstance(name, str)
            or not name.strip()
            or not isinstance(passed, bool)
            or not isinstance(message, str)
            or not message.strip()
        ):
            raise AccessibilityAuditError(
                "Accessibility audit returned an invalid check"
            )
        results.append(
            CheckResult(
                name=name,
                passed=passed,
                message=message[:MAX_AUDIT_MESSAGE_LENGTH],
            )
        )

    return tuple(results)
