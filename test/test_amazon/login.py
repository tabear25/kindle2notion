import asyncio
import pytest
from amazon import login
from amazon.login import AMAZON_NOTEBOOK_URL, EMAIL_SELECTOR, CONTINUE_SELECTOR, PASSWORD_SELECTOR, SIGNIN_SELECTOR, TWO_FACTOR_INPUT_SELECTOR, TWO_FACTOR_SUBMIT_SELECTOR, IDLE

# FakePageクラス：playwrightを模倣するためのダミークラス
class FakePage:
    def __init__(self):
        self.url = ""
        self.actions = []  
        self.selectors_called = {}
    
    def goto(self, url, timeout):
        self.actions.append(("goto", url))
        self.url = url

    def fill(self, selector, text):
        self.actions.append(("fill", selector, text))
        # 2段階認証の入力の場合、ここで入力値を記録する
        if selector == TWO_FACTOR_INPUT_SELECTOR:
            self.two_factor_code = text

    def click(self, selector):
        self.actions.append(("click", selector))
        if selector == TWO_FACTOR_SUBMIT_SELECTOR:
            self.url = AMAZON_NOTEBOOK_URL

    def wait_for_selector(self, selector, timeout):
        self.actions.append(("wait_for_selector", selector))
        if selector == TWO_FACTOR_INPUT_SELECTOR:
            return True
        return True

    def wait_for_load_state(self, state):
        self.actions.append(("wait_for_load_state", state))
        return True

# 正常系テスト：2段階認証完了後、ログインが成功するケース
@pytest.mark.asyncio
async def test_perform_login_success(monkeypatch):
    fake_page = FakePage()
    
    monkeypatch.setattr(login, "prompt_two_factor_code", lambda: "123456")
    
    await login.perform_login(fake_page, "dummy@example.com", "dummyPassword")
    
    fills = [action for action in fake_page.actions if action[0] == "fill"]
    two_factor_fills = [f for f in fills if f[1] == TWO_FACTOR_INPUT_SELECTOR and f[2] == "123456"]
    assert two_factor_fills, "2段階認証コードが正しく入力されていません。"
    
    assert fake_page.url.startswith(AMAZON_NOTEBOOK_URL), "最終URLが想定と異なります。"

# 異常系テスト：2段階認証完了後、最終的なURLが想定外の失敗ケース
@pytest.mark.asyncio
async def test_perform_login_failure(monkeypatch):
    fake_page = FakePage()
    
    # prompt_two_factor_code() のモック
    monkeypatch.setattr(login, "prompt_two_factor_code", lambda: "123456")
    
    original_click = fake_page.click
    def fake_click(selector):
        fake_page.actions.append(("click", selector))
        if selector == TWO_FACTOR_SUBMIT_SELECTOR:
            fake_page.url = "https://dummy-failure-url.com"
        else:
            original_click(selector)
    fake_page.click = fake_click

    with pytest.raises(Exception, match="Amazonへのログインに失敗しました。URLが想定と異なります。"):
        await login.perform_login(fake_page, "dummy@example.com", "dummyPassword")
