import tkinter as tk
from tkinter import messagebox, simpledialog

def show_popup_message(message: str, title = "完了通知") -> None:
    """
    GUIポップアップメッセージを表示する関数
    """
    root = tk.Tk()
    root.withdraw()  
    messagebox.showinfo(title, message)


def ask_book_limit(default: int = 3) -> int:
    """GUIから取得冊数を入力させる関数

    Parameters
    ----------
    default : int, optional
        入力がない場合に使用するデフォルト値, by default 3

    Returns
    -------
    int
        ユーザーが指定した取得冊数
    """
    root = tk.Tk()
    root.withdraw()
    limit = simpledialog.askinteger(
        "取得冊数",
        "取得する書籍数を入力してください",
        initialvalue=default,
        minvalue=1,
    )
    root.destroy()
    return limit if limit is not None else default
