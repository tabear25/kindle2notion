import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from amazon import login
from amazon.login import AMAZON_NOTEBOOK_URL, TWO_FACTOR_INPUT_SELECTOR, TWO_FACTOR_SUBMIT_SELECTOR


class FakePage:
    def __init__(self):
        self.url = ""
        self.actions = []

    def goto(self, url, timeout):
        self.actions.append(("goto", url, timeout))
        self.url = url

    def fill(self, selector, text):
        self.actions.append(("fill", selector, text))

    def click(self, selector):
        self.actions.append(("click", selector))
        if selector == TWO_FACTOR_SUBMIT_SELECTOR:
            self.url = AMAZON_NOTEBOOK_URL

    def wait_for_selector(self, selector, timeout):
        self.actions.append(("wait_for_selector", selector, timeout))
        return True

    def wait_for_load_state(self, state):
        self.actions.append(("wait_for_load_state", state))
        return True


def test_perform_login_success(monkeypatch):
    fake_page = FakePage()
    monkeypatch.setattr(login, "prompt_two_factor_code", lambda: "123456")

    login.perform_login(fake_page, "dummy@example.com", "dummyPassword")

    two_factor_fill = [
        action
        for action in fake_page.actions
        if action[0] == "fill" and action[1] == TWO_FACTOR_INPUT_SELECTOR and action[2] == "123456"
    ]
    assert two_factor_fill
    assert fake_page.url.startswith(AMAZON_NOTEBOOK_URL)


def test_perform_login_failure(monkeypatch):
    fake_page = FakePage()
    monkeypatch.setattr(login, "prompt_two_factor_code", lambda: "123456")

    original_click = fake_page.click

    def fake_click(selector):
        fake_page.actions.append(("click", selector))
        if selector == TWO_FACTOR_SUBMIT_SELECTOR:
            fake_page.url = "https://dummy-failure-url.com"
            return
        original_click(selector)

    fake_page.click = fake_click

    with pytest.raises(Exception):
        login.perform_login(fake_page, "dummy@example.com", "dummyPassword")
