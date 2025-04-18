import tkinter as tk
from tkinter import messagebox

def show_popup_message(message: str, title = "完了通知") -> None:
    """
    GUIポップアップメッセージを表示する関数
    """
    root = tk.Tk()
    root.withdraw()  
    messagebox.showinfo(title, message)
    root.destroy()  