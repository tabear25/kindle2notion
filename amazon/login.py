import time

AMAZON_NOTEBOOK_URL = "https://read.amazon.co.jp/notebook"
EMAIL_SELECTOR = "#ap_email_login"
CONTINUE_SELECTOR = "#continue > span > input"
PASSWORD_SELECTOR = "#ap_password"
SIGNIN_SELECTOR = "#signInSubmit"
TWO_FACTOR_INPUT_SELECTOR = "#auth-mfa-otpcode"
TWO_FACTOR_SUBMIT_SELECTOR = "#auth-signin-button"
NOTEBOOK_READY_SELECTOR = ".kp-notebook-library-each-book"
LOAD_TIMEOUT = 15000
SESSION_CHECK_TIMEOUT_MS = 10000
NOTEBOOK_WAIT_TIMEOUT = 180000
POLL_INTERVAL_SECONDS = 0.5
RACE_POLL_INTERVAL_MS = 250
MAX_2FA_ATTEMPTS = 5
TWO_FACTOR_REJECTED_MESSAGE = "コードが誤っていました。もう一度入力してください。"


def _is_visible(page, selector: str) -> bool:
    try:
        element = page.query_selector(selector)
        return bool(element and element.is_visible())
    except Exception:
        return False


def _wait_for_first_visible(page, selectors, timeout_ms: int,
                            poll_ms: int = RACE_POLL_INTERVAL_MS):
    """Poll until one of ``selectors`` is visible; return it, or None on timeout.

    ``selectors`` order is the priority when several are visible at once.
    Checks at least once, so a zero timeout still sees the current state.
    """
    deadline = time.time() + (timeout_ms / 1000)
    while True:
        for selector in selectors:
            if _is_visible(page, selector):
                return selector
        if time.time() >= deadline:
            return None
        page.wait_for_timeout(poll_ms)


def _wait_until_hidden(page, selector: str, timeout_ms: int,
                       poll_ms: int = RACE_POLL_INTERVAL_MS) -> bool:
    """Poll until ``selector`` is no longer visible. True on success."""
    deadline = time.time() + (timeout_ms / 1000)
    while True:
        if not _is_visible(page, selector):
            return True
        if time.time() >= deadline:
            return False
        page.wait_for_timeout(poll_ms)


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


def is_session_valid(page, timeout_ms: int = SESSION_CHECK_TIMEOUT_MS) -> bool:
    """Probe whether the page's storage state still reaches the notebook.

    Loads the notebook URL and races the library list against the sign-in
    form. Only a visible library counts as a valid session; any doubt
    (timeout, navigation error) reports False so the caller falls back to a
    normal login.
    """
    try:
        page.goto(AMAZON_NOTEBOOK_URL, timeout=LOAD_TIMEOUT)
    except Exception:
        return False
    matched = _wait_for_first_visible(
        page,
        [NOTEBOOK_READY_SELECTOR, EMAIL_SELECTOR, PASSWORD_SELECTOR],
        timeout_ms,
    )
    return matched == NOTEBOOK_READY_SELECTOR


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


def _handle_two_factor(page, two_factor_callback, allow_manual_auth: bool) -> None:
    if allow_manual_auth and two_factor_callback is None:
        # Visible browser: the user completes 2FA (or any extra challenge)
        # directly on the page.
        _wait_for_notebook_ready(page)
        return

    if two_factor_callback is None:
        from gui_utils.gui import prompt_two_factor_code

        two_factor_callback = prompt_two_factor_code

    last_error: str | None = None
    for _attempt in range(MAX_2FA_ATTEMPTS):
        code = two_factor_callback(error_message=last_error)
        if code is None:
            raise SystemExit("Cancelled by user during two-factor authentication.")

        page.fill(TWO_FACTOR_INPUT_SELECTOR, code)
        page.click(TWO_FACTOR_SUBMIT_SELECTOR)

        if _wait_until_hidden(page, TWO_FACTOR_INPUT_SELECTOR, LOAD_TIMEOUT):
            return
        last_error = TWO_FACTOR_REJECTED_MESSAGE

    raise SystemExit("2FA failed: maximum attempts exceeded.")


def perform_login(page, amazon_email, amazon_password, two_factor_callback=None, allow_manual_auth=False):
    page.goto(AMAZON_NOTEBOOK_URL, timeout=LOAD_TIMEOUT)

    _fill_if_visible(page, EMAIL_SELECTOR, amazon_email)
    _click_if_visible(page, CONTINUE_SELECTOR)

    # Race the possible next states instead of waiting a full timeout for
    # each in sequence: an already-authenticated session jumps straight to
    # the notebook, a no-2FA account skips the OTP wait entirely.
    matched = _wait_for_first_visible(
        page,
        [PASSWORD_SELECTOR, TWO_FACTOR_INPUT_SELECTOR, NOTEBOOK_READY_SELECTOR],
        LOAD_TIMEOUT,
    )

    if matched == PASSWORD_SELECTOR:
        page.fill(PASSWORD_SELECTOR, amazon_password)
        page.click(SIGNIN_SELECTOR)
        matched = _wait_for_first_visible(
            page,
            [TWO_FACTOR_INPUT_SELECTOR, NOTEBOOK_READY_SELECTOR],
            LOAD_TIMEOUT,
        )

    if matched == TWO_FACTOR_INPUT_SELECTOR:
        _handle_two_factor(page, two_factor_callback, allow_manual_auth)

    _wait_for_notebook_ready(page)
