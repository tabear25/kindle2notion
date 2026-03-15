import tkinter as tk
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

def prompt_two_factor_code():
    root = tk.Tk()
    root.geometry("300x150")
    root.title("2FA Code")
    root.configure(bg="lightblue")

    code_var = tk.StringVar()
    label = tk.Label(
        root,
        text="Enter your 2FA code:",
        bg="lightblue",
        font=("Arial", 12),
    )
    label.pack(pady=10)

    entry = tk.Entry(root, textvariable=code_var, width=20, font=("Arial", 14))
    entry.pack(pady=10)
    entry.focus_set()

    def submit(event=None):
        root.quit()

    button = tk.Button(root, text="Submit", command=submit, font=("Arial", 12))
    button.pack(pady=10)
    entry.bind("<Return>", submit)

    root.mainloop()
    code = code_var.get()
    root.destroy()
    return code

def perform_login(page, amazon_email, amazon_password):
    page.goto(AMAZON_NOTEBOOK_URL, timeout=LOAD_TIMEOUT)
    page.fill(EMAIL_SELECTOR, amazon_email)
    page.click(CONTINUE_SELECTOR)
    page.wait_for_selector(PASSWORD_SELECTOR, timeout=LOAD_TIMEOUT)
    page.fill(PASSWORD_SELECTOR, amazon_password)
    page.click(SIGNIN_SELECTOR)

    try:
        page.wait_for_selector(TWO_FACTOR_INPUT_SELECTOR, timeout=LOAD_TIMEOUT)
        code = prompt_two_factor_code()
        if code:
            page.fill(TWO_FACTOR_INPUT_SELECTOR, code)
            page.click(TWO_FACTOR_SUBMIT_SELECTOR)
    except PlaywrightTimeoutError:
        pass

    page.wait_for_load_state(IDLE)

    if not page.url.startswith(AMAZON_NOTEBOOK_URL):
        raise Exception("Amazon login failed. Please check your credentials and 2FA flow.")
