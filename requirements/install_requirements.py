# 仮想環境を使用している場合はコメントアウトを解除して以下のコードを実行することで必要なパッケージをインストール可能

### ""
# import subprocess
# import sys

# def install_requirements():
#     try:
#         subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
#     except subprocess.CalledProcessError:
#         print("Error occurred during the installation of required packages.")
#         sys.exit(1)

# if __name__ == "__main__":
#     install_requirements()