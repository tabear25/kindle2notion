import tkinter as tk

# ログインのブラウザ操作に必要なCSSセレクター
AMAZON_NOTEBOOK_URL = "https://read.amazon.co.jp/notebook"
EMAIL_SELECTOR = 'input#ap_email'
CONTINUE_SELECTOR = 'input#continue'
PASSWORD_SELECTOR = 'input#ap_password'
SIGNIN_SELECTOR = 'input#signInSubmit'
TWO_FACTOR_INPUT_SELECTOR = "#auth-mfa-otpcode"
TWO_FACTOR_SUBMIT_SELECTOR = "#auth-signin-button"
IDLE = 'networkidle'
LOAD_TIMEOUT = 15000

def prompt_two_factor_code():
    root = tk.Tk()
    root.geometry("300x150")
    root.title("2段階認証コード入力")
    root.configure(bg='lightblue')
    
    code_var = tk.StringVar()
    
    label = tk.Label(root, text="2段階認証コードを入力してください:", bg='lightblue', font=('Arial', 12))
    label.pack(pady=10)
    
    entry = tk.Entry(root, textvariable=code_var, width=20, font=('Arial', 14))
    entry.pack(pady=10)
    entry.focus_set()
    
    def submit(event=None):
        root.quit()  
    
    button = tk.Button(root, text="送信", command=submit, font=('Arial', 12))
    button.pack(pady=10)
    
    entry.bind("<Return>", submit)
    
    root.mainloop()
    code = code_var.get()
    root.destroy()
    return code

def perform_login(page, AMAZON_EMAIL, AMAZON_PASSWORD):
    page.goto(AMAZON_NOTEBOOK_URL, timeout=LOAD_TIMEOUT)
    page.fill(EMAIL_SELECTOR, AMAZON_EMAIL)
    page.click(CONTINUE_SELECTOR)
    page.wait_for_selector(PASSWORD_SELECTOR, timeout=LOAD_TIMEOUT)
    page.fill(PASSWORD_SELECTOR, AMAZON_PASSWORD)
    page.click(SIGNIN_SELECTOR)
    
    try:
        page.wait_for_selector(TWO_FACTOR_INPUT_SELECTOR, timeout=LOAD_TIMEOUT)
    except RuntimeError as re:
        print("RuntimeErrorを検出しましたが無視して継続します。:", re)
        pass
    except Exception as e:
        raise Exception("2段階認証コード入力画面が表示されませんでした。") from e
    
    print("2段階認証コード入力用のGUIを表示します。")
    code = prompt_two_factor_code()
    
    page.fill(TWO_FACTOR_INPUT_SELECTOR, code)
    page.click(TWO_FACTOR_SUBMIT_SELECTOR)
    
    page.wait_for_load_state(IDLE)
    
    if not page.url.startswith(AMAZON_NOTEBOOK_URL):
        raise Exception("Amazonへのログインに失敗しました。URLが想定と異なります。")
    
    print("Amazonへのログインに成功しました。")
