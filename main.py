import os
import asyncio
import tkinter as tk
from tkinter import messagebox, simpledialog

import nest_asyncio
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

import amazon.login
from book_transformer import transformer
from notion import toNotion

nest_asyncio.apply()

load_dotenv("config/KEYS.env")
AMAZON_EMAIL = os.getenv("AMAZON_EMAIL")
AMAZON_PASSWORD = os.getenv("AMAZON_PASSWORD")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

required_env_vars = [AMAZON_EMAIL, AMAZON_PASSWORD, NOTION_API_KEY, NOTION_DATABASE_ID]
if not all(required_env_vars):
    raise ValueError(
        "Missing required environment variables. Please set AMAZON_EMAIL, AMAZON_PASSWORD, "
        "NOTION_API_KEY, and NOTION_DATABASE_ID in config/KEYS.env."
    )


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


def run(playwright, max_books=None):
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()

    try:
        asyncio.run(amazon.login.perform_login(page, AMAZON_EMAIL, AMAZON_PASSWORD))
        context.storage_state(path="storage_state.json")
    finally:
        browser.close()

    headless_browser = playwright.chromium.launch(headless=True)
    headless_context = headless_browser.new_context(storage_state="storage_state.json")
    headless_page = headless_context.new_page()

    try:
        notes = transformer.extract_notes(headless_page, max_books=max_books)
        return notes
    finally:
        headless_browser.close()


if __name__ == "__main__":
    max_books = prompt_book_limit()
    with sync_playwright() as p:
        notes = run(p, max_books=max_books)
        toNotion.save_notes_to_notion(NOTION_API_KEY, NOTION_DATABASE_ID, notes)
        print("Saved notes to Notion.")
