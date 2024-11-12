import time

def perform_login(page, email, password):
    page.goto("https://read.amazon.co.jp/notebook", timeout=60000)
    page.fill('input#ap_email', email)
    page.click('input#continue')
    page.wait_for_selector('input#ap_password', timeout=10000)

    page.fill('input#ap_password', password)
    page.click('input#signInSubmit')

    print('ログインのために2段階認証コードを入力してください。60秒待機します。')
    page.wait_for_timeout(60000)

    page.wait_for_load_state('networkidle')
    if not page.url.startswith("https://read.amazon.co.jp/notebook"):
        raise Exception("Amazonへのログインに失敗しました。")
    print("Amazonへのログインに成功しました。")