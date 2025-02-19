import time

AMAZON_NOTEBOOK_URL = "https://read.amazon.co.jp/notebook"
EMAIL_SELECTOR = 'input#ap_email'
CONTINUE_SELECTOR = 'input#continue'
PASSWORD_SELECTOR = 'input#ap_password'
SIGNIN_SELECTOR = 'input#signInSubmit'
TWO_FACTOR_WAIT_MS = 45000  
LOAD_TIMEOUT = 30000  

def perform_login(page, email, password):
    # ログイン処理
    page.goto(AMAZON_NOTEBOOK_URL, timeout=LOAD_TIMEOUT)
    page.fill(EMAIL_SELECTOR, email)
    page.click(CONTINUE_SELECTOR)
    page.wait_for_selector(PASSWORD_SELECTOR, timeout=10000)
    page.fill(PASSWORD_SELECTOR, password)
    page.click(SIGNIN_SELECTOR)
    
    # 2段階認証
    print('ログインのために2段階認証コードを入力してください。45秒待機します。')
    page.wait_for_timeout(TWO_FACTOR_WAIT_MS)
    page.wait_for_load_state('networkidle')
    
    if not page.url.startswith(AMAZON_NOTEBOOK_URL):
        raise Exception("Amazonへのログインに失敗しました。URLが想定と異なります。")
    
    print("Amazonへのログインに成功しました。")
