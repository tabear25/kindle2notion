import time

AMAZON_NOTEBOOK_URL = "https://www.amazon.co.jp/ap/signin?openid.pape.max_auth_age=3600&openid.return_to=https%3A%2F%2Fread.amazon.co.jp%2Fnotebook&openid.identity=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.assoc_handle=amzn_kp_mobile_jp&openid.mode=checkid_setup&language=ja_JP&openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0&dplnkId=81a7fc67-9ebd-4d80-91eb-7e324e8c8be0" 
EMAIL_SELECTOR = 'input#ap_email'
CONTINUE_SELECTOR = 'input#continue'
PASSWORD_SELECTOR = 'input#ap_password'
SIGNIN_SELECTOR = 'input#signInSubmit'
IDLE = 'networkidle'
TWO_FACTOR_WAIT = "https://read.amazon.co.jp/notebook?openid.assoc_handle=amzn_kp_mobile_jp&openid.claimed_id=https%3A%2F%2Fwww.amazon.co.jp%2Fap%2Fid%2Famzn1.account.AF6SDO53KVEPLL3Q7YPOMA2NINGA&openid.identity=https%3A%2F%2Fwww.amazon.co.jp%2Fap%2Fid%2Famzn1.account.AF6SDO53KVEPLL3Q7YPOMA2NINGA&openid.mode=id_res&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0&openid.op_endpoint=https%3A%2F%2Fwww.amazon.co.jp%2Fap%2Fsignin&openid.response_nonce=2025-03-15T00%3A03%3A14Z5065609785765237201&openid.return_to=https%3A%2F%2Fread.amazon.co.jp%2Fnotebook&openid.signed=assoc_handle%2Cclaimed_id%2Cidentity%2Cmode%2Cns%2Cop_endpoint%2Cresponse_nonce%2Creturn_to%2Cns.pape%2Cpape.auth_policies%2Cpape.auth_time%2Csigned&openid.ns.pape=http%3A%2F%2Fspecs.openid.net%2Fextensions%2Fpape%2F1.0&openid.pape.auth_policies=http%3A%2F%2Fschemas.openid.net%2Fpape%2Fpolicies%2F2007%2F06%2Fmulti-factor&openid.pape.auth_time=2025-03-15T00%3A03%3A02Z&openid.sig=VviAOXimFVnzd13PmKm3FvqUBCsCL2KuJ4naeZ6Bvos%3D&serial="
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
    page.wait_for_timeout(TWO_FACTOR_WAIT)
    page.wait_for_load_state(IDLE)
    
    if not page.url.startswith(AMAZON_NOTEBOOK_URL):
        raise Exception("Amazonへのログインに失敗しました。URLが想定と異なります。")
    
    print("Amazonへのログインに成功しました。")
