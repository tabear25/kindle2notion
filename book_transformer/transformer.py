from tqdm import tqdm
import time
import re
from tqdm import tqdm

def extract_notes(page, max_books: int = 3):
    """Extract highlights from Kindle Notebook.

    Parameters
    ----------
    page : playwright.sync_api.Page
        Logged-in page instance.
    max_books : int, optional
        Number of books to extract, by default 3.
    """
    page.goto("https://read.amazon.co.jp/notebook", timeout=60000)
    each_books = page.query_selector_all('.kp-notebook-library-each-book')
    total_books = len(each_books)
    books_to_process = each_books[:limit] if limit else each_books

    notes = []  
    """
    enumerate(each_books[:max_books])、各書籍のハイライトを取得するために、何冊分の書籍を取得するかを指定します。
    enumerate(each_books[:max_books])は、最初の指定された冊数の書籍を取得することを意味します。
    もし全ての書籍を取得したい場合は、enumerate(each_books)としてください。
    """
    for index, book in enumerate(each_books[:3]):
        text_array = []
        book.click()
        time.sleep(5)  

        book_title_element = page.query_selector('h3')
        if book_title_element:
            book_title = book_title_element.text_content().strip()
        else:
            book_title = f"Unknown Book {index + 1}"
            print(f"警告: 書籍 {index + 1} のタイトルが見つかりませんでした。")

        highlights = page.query_selector_all('#highlight')

        for highlight in highlights:
            content = highlight.text_content().strip()
            page_info_element = highlight.query_selector('#annotationHighlightHeader')
            if page_info_element:
                page_info_text = page_info_element.text_content().strip()
                match = re.search(r"\d+", page_info_text)
                if match:
                    page_number = match.group(0)
                else:
                    page_number = ""
            else:
                page_number = ""
                
            text_array.append(content)
            note = {
                "title": book_title,
                "content": content,
                "page": page_number
            }
            notes.append(note)

    return notes
