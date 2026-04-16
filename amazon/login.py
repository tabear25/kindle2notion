from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

AMAZON_NOTEBOOK_URL = "https://read.amazon.co.jp/notebook"
EMAIL_SELECTOR = "#ap_email_login"
CONTINUE_SELECTOR = "#continue > span > input"
PASSWORD_SELECTOR = "#ap_password"
SIGNIN_SELECTOR = "#signInSubmit"
TWO_FACTOR_INPUT_SELECTOR = "#auth-mfa-otpcode"
TWO_FACTOR_SUBMIT_SELECTOR = "#auth-signin-button"
IDLE = "networkidle"
LOAD_TIMEOUT = 15000

def perform_login(page, amazon_email, amazon_password, two_factor_callback=None):
    if two_factor_callback is None:
        from gui_utils.gui import prompt_two_factor_code
        two_factor_callback = prompt_two_factor_code

    page.goto(AMAZON_NOTEBOOK_URL, timeout=LOAD_TIMEOUT)
    page.fill(EMAIL_SELECTOR, amazon_email)
    page.click(CONTINUE_SELECTOR)
    page.wait_for_selector(PASSWORD_SELECTOR, timeout=LOAD_TIMEOUT)
    page.fill(PASSWORD_SELECTOR, amazon_password)
    page.click(SIGNIN_SELECTOR)

    try:
        page.wait_for_selector(TWO_FACTOR_INPUT_SELECTOR, timeout=LOAD_TIMEOUT)
        code = two_factor_callback()
        if code is None:
            raise SystemExit("Cancelled by user during two-factor authentication.")
        page.fill(TWO_FACTOR_INPUT_SELECTOR, code)
        page.click(TWO_FACTOR_SUBMIT_SELECTOR)
    except PlaywrightTimeoutError:
        pass

    page.wait_for_load_state(IDLE)

    if not page.url.startswith(AMAZON_NOTEBOOK_URL):
        raise Exception("Amazon login failed. Please check your credentials and 2FA flow.")
