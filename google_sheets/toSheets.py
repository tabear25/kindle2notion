import json

import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import WorksheetNotFound
from tqdm import tqdm

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
HEADERS = ["Title", "Content", "Page"]


def _build_client(service_account_file):
    service_account_source = (service_account_file or "").strip()
    if not service_account_source:
        raise ValueError("Google service account credential is empty.")

    if service_account_source.startswith("{"):
        credentials_info = json.loads(service_account_source)
        credentials = Credentials.from_service_account_info(
            credentials_info,
            scopes=SCOPES,
        )
    else:
        credentials = Credentials.from_service_account_file(
            service_account_source,
            scopes=SCOPES,
        )
    return gspread.authorize(credentials)


def _get_or_create_worksheet(spreadsheet, worksheet_name):
    try:
        worksheet = spreadsheet.worksheet(worksheet_name)
    except WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=worksheet_name, rows=1000, cols=10)
    return worksheet


def _ensure_header_row(worksheet):
    first_row = worksheet.row_values(1)
    if not first_row:
        worksheet.append_row(HEADERS, value_input_option="RAW")


def _get_existing_contents(worksheet):
    column_values = worksheet.col_values(2)
    if not column_values:
        return set()

    start_index = 1 if column_values[0].strip() == "Content" else 0
    return {value for value in column_values[start_index:] if value.strip()}


def save_notes_to_google_sheets(service_account_file, spreadsheet_id, worksheet_name, notes, progress_callback=None):
    client = _build_client(service_account_file)
    spreadsheet = client.open_by_key(spreadsheet_id)
    worksheet = _get_or_create_worksheet(spreadsheet, worksheet_name)
    _ensure_header_row(worksheet)
    existing_contents = _get_existing_contents(worksheet)

    rows_to_append = []
    for i, note in enumerate(tqdm(notes, desc="Sheets")):
        if progress_callback:
            progress_callback("sheets", i + 1, len(notes), note.get("title", ""))
        content = note.get("content", "")
        if not content or content in existing_contents:
            continue

        rows_to_append.append(
            [
                note.get("title", ""),
                content,
                note.get("page", ""),
            ]
        )
        existing_contents.add(content)

    if not rows_to_append:
        return

    try:
        worksheet.append_rows(rows_to_append, value_input_option="RAW")
    except Exception as e:
        failed_count = len(rows_to_append)
        print(f"Failed to save notes to Google Sheets ({failed_count} rows): {e}")
