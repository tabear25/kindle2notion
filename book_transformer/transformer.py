import re

NOTEBOOK_URL = "https://read.amazon.co.jp/notebook"
BOOK_SELECTOR = ".kp-notebook-library-each-book"
BOOK_TITLE_SELECTOR = "h3"
HIGHLIGHT_SELECTOR = "#highlight"
PAGE_INFO_SELECTOR = "#annotationHighlightHeader"
BOOK_SWITCH_WAIT_MS = 1500
LOAD_TIMEOUT = 60000


def _get_book_elements(page):
    return page.query_selector_all(BOOK_SELECTOR)


def extract_notes(page, max_books=None, progress_callback=None):
    page.goto(NOTEBOOK_URL, timeout=LOAD_TIMEOUT)
    page.wait_for_selector(BOOK_SELECTOR, timeout=LOAD_TIMEOUT)

    books = _get_book_elements(page)
    total_books = len(books) if max_books is None else min(len(books), max_books)
    notes = []

    for index in range(total_books):
        books = _get_book_elements(page)
        books[index].click()
        page.wait_for_timeout(BOOK_SWITCH_WAIT_MS)
        page.wait_for_selector(BOOK_TITLE_SELECTOR, timeout=LOAD_TIMEOUT)

        book_title_element = page.query_selector(BOOK_TITLE_SELECTOR)
        if book_title_element:
            book_title = (book_title_element.text_content() or "").strip()
        else:
            book_title = f"Unknown Book {index + 1}"
            print(f"Warning: title not found for book {index + 1}.")

        if progress_callback:
            progress_callback(
                "scrape",
                index + 1,
                total_books,
                f"「{book_title}」のハイライトを取得中...",
            )

        highlights = page.query_selector_all(HIGHLIGHT_SELECTOR)
        for highlight in highlights:
            content = (highlight.text_content() or "").strip()
            if not content:
                continue

            page_info_element = highlight.query_selector(PAGE_INFO_SELECTOR)
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
