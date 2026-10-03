from autonomous_qa.browser.observation import (
    INTERACTIVE_SELECTOR,
    OBSERVATION_LIMIT,
    OPTION_LIMIT,
    OPTION_VALUE_LIMIT,
    observe_page,
)


class FakeLocator:
    def evaluate_all(self, script: str, options: dict) -> dict:
        assert script
        assert options == {
            "limit": OBSERVATION_LIMIT,
            "labelLimit": 160,
            "optionLimit": OPTION_LIMIT,
            "optionValueLimit": OPTION_VALUE_LIMIT,
        }
        return {
            "truncated": False,
            "elements": [
                {
                    "selector": "#submit",
                    "tag": "button",
                    "role": "button",
                    "label": "Submit",
                    "input_type": None,
                    "disabled": False,
                    "href": None,
                    "options": [],
                },
                {
                    "selector": "#country",
                    "tag": "select",
                    "role": "combobox",
                    "label": "Country",
                    "input_type": None,
                    "disabled": False,
                    "href": None,
                    "options": ["eg", "uk"],
                    "checked": None,
                },
                {
                    "selector": "#terms",
                    "tag": "input",
                    "role": "checkbox",
                    "label": "Accept terms",
                    "input_type": "checkbox",
                    "disabled": False,
                    "href": None,
                    "options": [],
                    "checked": True,
                }
            ],
        }


class FakePage:
    def locator(self, selector: str) -> FakeLocator:
        assert selector == INTERACTIVE_SELECTOR
        return FakeLocator()


def test_observe_page_converts_browser_data_to_typed_models() -> None:
    observation = observe_page(FakePage())

    assert observation.truncated is False
    assert len(observation.elements) == 3
    assert observation.elements[0].selector == "#submit"
    assert observation.elements[0].label == "Submit"
    assert observation.elements[1].options == ("eg", "uk")
    assert observation.elements[2].checked is True
