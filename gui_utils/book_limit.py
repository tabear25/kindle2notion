import tkinter as tk
from tkinter import messagebox, simpledialog

def prompt_book_limit():
    root = tk.Tk()
    root.withdraw()

    while True:
        value = simpledialog.askstring(
            "Book Count",
            "How many books do you want to scrape?\n"
            "Enter a positive integer. Leave blank for all books.",
            parent=root,
        )

        if value is None:
            root.destroy()
            raise SystemExit("Cancelled by user.")

        value = value.strip()
        if value == "":
            root.destroy()
            return None

        if value.isdigit() and int(value) > 0:
            root.destroy()
            return int(value)

        messagebox.showerror(
            "Invalid Input",
            "Please enter a positive integer, or leave blank for all books.",
            parent=root,
        )
