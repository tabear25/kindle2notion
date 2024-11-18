import pyotp

raw_key = "YOUR_TWO-FACTOR-KEY"

# 空白を削除してBase32形式に変換
base32_key = raw_key.replace(" ", "")

totp = pyotp.TOTP(base32_key)
print("Current OTP:", totp.now())
