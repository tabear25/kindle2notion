import time

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

AMAZON_NOTEBOOK_URL = "https://read.amazon.co.jp/notebook"
EMAIL_SELECTOR = "#ap_email_login"
CONTINUE_SELECTOR = "#continue > span > input"
PASSWORD_SELECTOR = "#ap_password"
SIGNIN_SELECTOR = "#signInSubmit"
TWO_FACTOR_INPUT_SELECTOR = "#auth-mfa-otpcode"
TWO_FACTOR_SUBMIT_SELECTOR = "#auth-signin-button"
NOTEBOOK_READY_SELECTOR = ".kp-notebook-library-each-book"
LOAD_TIMEOUT = 15000
NOTEBOOK_WAIT_TIMEOUT = 180000
POLL_INTERVAL_SECONDS = 0.5


def _is_visible(page, selector: str) -> bool:
    try:
        element = page.query_selector(selector)
        return bool(element and element.is_visible())
    except Exception:
        return False


def _wait_for_notebook_ready(page, timeout_ms: int = NOTEBOOK_WAIT_TIMEOUT) -> None:
    deadline = time.time() + (timeout_ms / 1000)

    while time.time() < deadline:
        if page.url.startswith(AMAZON_NOTEBOOK_URL) and _is_visible(page, NOTEBOOK_READY_SELECTOR):
            return
        page.wait_for_timeout(int(POLL_INTERVAL_SECONDS * 1000))

    raise TimeoutError(
        "Amazon login did not reach the Kindle Notebook page. "
        "Complete login in the browser and try again."
    )


def _fill_if_visible(page, selector: str, value: str) -> bool:
    if not _is_visible(page, selector):
        return False
    page.fill(selector, value)
    return True


def _click_if_visible(page, selector: str) -> bool:
    if not _is_visible(page, selector):
        return False
    page.click(selector)
    return True


def perform_login(page, amazon_email, amazon_password, two_factor_callback=None, allow_manual_auth=False):
    page.goto(AMAZON_NOTEBOOK_URL, timeout=LOAD_TIMEOUT)

    _fill_if_visible(page, EMAIL_SELECTOR, amazon_email)
    _click_if_visible(page, CONTINUE_SELECTOR)

    try:
        page.wait_for_selector(PASSWORD_SELECTOR, timeout=LOAD_TIMEOUT)
        page.fill(PASSWORD_SELECTOR, amazon_password)
        page.click(SIGNIN_SELECTOR)
    except PlaywrightTimeoutError:
        # The page may already have an authenticated session.
        pass

    try:
        page.wait_for_selector(TWO_FACTOR_INPUT_SELECTOR, timeout=LOAD_TIMEOUT)
        if allow_manual_auth and two_factor_callback is None:
            _wait_for_notebook_ready(page)
            return

        if two_factor_callback is None:
            from gui_utils.gui import prompt_two_factor_code

            two_factor_callback = prompt_two_factor_code

        code = two_factor_callback()
        if code is None:
            raise SystemExit("Cancelled by user during two-factor authentication.")

        page.fill(TWO_FACTOR_INPUT_SELECTOR, code)
        page.click(TWO_FACTOR_SUBMIT_SELECTOR)
    except PlaywrightTimeoutError:
        pass

    _wait_for_notebook_ready(page)
