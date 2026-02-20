import re
import time


def extract_notes(page, max_books=None):
    page.goto("https://read.amazon.co.jp/notebook", timeout=60000)
    each_books = page.query_selector_all(".kp-notebook-library-each-book")
    if max_books is not None:
        each_books = each_books[:max_books]

    notes = []
    for index, book in enumerate(each_books):
        book.click()
        time.sleep(5)

        book_title_element = page.query_selector("h3")
        if book_title_element:
            book_title = (book_title_element.text_content() or "").strip()
        else:
            book_title = f"Unknown Book {index + 1}"
            print(f"Warning: title not found for book {index + 1}.")

        highlights = page.query_selector_all("#highlight")

        for highlight in highlights:
            content = (highlight.text_content() or "").strip()
            if not content:
                continue

            page_info_element = highlight.query_selector("#annotationHighlightHeader")
            page_number = ""
            if page_info_element:
                page_info_text = (page_info_element.text_content() or "").strip()
                match = re.search(r"\d+", page_info_text)
                if match:
                    page_number = match.group(0)

            notes.append(
                {
                    "title": book_title,
                    "content": content,
                    "page": page_number,
                }
            )

    return notes
