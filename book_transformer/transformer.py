import time
import re

def extract_notes(page):
    page.goto("https://read.amazon.co.jp/notebook", timeout=60000)
    each_books = page.query_selector_all('.kp-notebook-library-each-book')

    notes = []  
    for index, book in enumerate(each_books):
        text_array = []
        book.click()
        time.sleep(7)  

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
                match = re.search(r"[:：]\s*(\d{1,5})", page_info_text)
                if match:
                    page_number = match.group(1)
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