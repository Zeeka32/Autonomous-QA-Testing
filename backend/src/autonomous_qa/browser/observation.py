from playwright.sync_api import Page

from ..models import InteractiveElement, PageObservation


OBSERVATION_LIMIT = 100
OPTION_LIMIT = 50
OPTION_VALUE_LIMIT = 160
INTERACTIVE_SELECTOR = ", ".join(
    [
        "a[href]",
        "button",
        "input",
        "textarea",
        "select",
        "[contenteditable='true']",
        "[role='button']",
        "[role='link']",
        "[role='checkbox']",
        "[role='radio']",
        "[role='tab']",
    ]
)

OBSERVATION_SCRIPT = r"""
(elements, options) => {
  const normalize = (value) => (value || "").replace(/\s+/g, " ").trim();
  const visible = (element) => {
    const style = window.getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.visibility !== "hidden" &&
      style.display !== "none" &&
      rect.width > 0 &&
      rect.height > 0;
  };
  const unique = (selector) => document.querySelectorAll(selector).length === 1;
  const selectorFor = (element) => {
    if (element.id) {
      const selector = `#${CSS.escape(element.id)}`;
      if (unique(selector)) return selector;
    }

    for (const attribute of ["data-testid", "name", "aria-label"]) {
      const value = element.getAttribute(attribute);
      if (value) {
        const tag = element.tagName.toLowerCase();
        const escapedValue = CSS.escape(value);
        const selector = `${tag}[${attribute}="${escapedValue}"]`;
        if (unique(selector)) return selector;
      }
    }

    const parts = [];
    let current = element;
    while (current && current.nodeType === Node.ELEMENT_NODE) {
      let part = current.tagName.toLowerCase();
      if (current.id) {
        part = `#${CSS.escape(current.id)}`;
        parts.unshift(part);
        break;
      }
      const siblings = Array.from(current.parentElement?.children || [])
        .filter((sibling) => sibling.tagName === current.tagName);
      if (siblings.length > 1) {
        part += `:nth-of-type(${siblings.indexOf(current) + 1})`;
      }
      parts.unshift(part);
      current = current.parentElement;
    }
    return parts.join(" > ");
  };
  const implicitRole = (element) => {
    const tag = element.tagName.toLowerCase();
    if (tag === "a") return "link";
    if (tag === "button") return "button";
    if (tag === "textarea") return "textbox";
    if (tag === "select") return "combobox";
    if (tag !== "input") return null;
    const type = (element.getAttribute("type") || "text").toLowerCase();
    if (type === "checkbox") return "checkbox";
    if (type === "radio") return "radio";
    if (["button", "submit", "reset"].includes(type)) return "button";
    return "textbox";
  };
  const checkedFor = (element) => {
    if (element.tagName.toLowerCase() !== "input") return null;
    const type = (element.getAttribute("type") || "text").toLowerCase();
    return ["checkbox", "radio"].includes(type)
      ? Boolean(element.checked)
      : null;
  };
  const labelFor = (element) => {
    const labels = Array.from(element.labels || [])
      .map((label) => label.textContent)
      .join(" ");
    return normalize(
      element.getAttribute("aria-label") ||
      labels ||
      element.getAttribute("placeholder") ||
      element.innerText ||
      element.textContent ||
      element.getAttribute("title")
    ).slice(0, options.labelLimit);
  };

  const visibleElements = elements.filter(visible);
  return {
    truncated: visibleElements.length > options.limit,
    elements: visibleElements.slice(0, options.limit).map((element) => ({
      selector: selectorFor(element),
      tag: element.tagName.toLowerCase(),
      role: element.getAttribute("role") || implicitRole(element),
      label: labelFor(element),
      input_type: element.tagName.toLowerCase() === "input"
        ? (element.getAttribute("type") || "text").toLowerCase()
        : null,
      disabled: Boolean(element.disabled) ||
        element.getAttribute("aria-disabled") === "true",
      href: element.tagName.toLowerCase() === "a" ? element.href : null,
      options: element.tagName.toLowerCase() === "select"
        ? Array.from(element.options)
            .filter((option) =>
              !option.disabled &&
              option.value.length <= options.optionValueLimit
            )
            .slice(0, options.optionLimit)
            .map((option) => option.value)
        : [],
      checked: checkedFor(element),
    })),
  };
}
"""


def observe_page(page: Page) -> PageObservation:
    raw_observation = page.locator(INTERACTIVE_SELECTOR).evaluate_all(
        OBSERVATION_SCRIPT,
        {
            "limit": OBSERVATION_LIMIT,
            "labelLimit": 160,
            "optionLimit": OPTION_LIMIT,
            "optionValueLimit": OPTION_VALUE_LIMIT,
        },
    )
    elements = tuple(
        InteractiveElement(
            **{
                **raw_element,
                "options": tuple(raw_element["options"]),
            }
        )
        for raw_element in raw_observation["elements"]
    )
    return PageObservation(
        elements=elements,
        truncated=raw_observation["truncated"],
    )
