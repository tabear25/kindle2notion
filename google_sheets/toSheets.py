import json

import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import WorksheetNotFound
from tqdm import tqdm

from note_utils import build_note_key, build_note_key_from_note, has_any_note_value, note_to_row

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


def _get_existing_note_keys(worksheet):
    rows = worksheet.get_all_values()
    if not rows:
        return set()

    start_index = 1 if rows[0][: len(HEADERS)] == HEADERS else 0
    note_keys = set()
    for row in rows[start_index:]:
        padded_row = (row + ["", "", ""])[: len(HEADERS)]
        if has_any_note_value(padded_row):
            note_keys.add(build_note_key(*padded_row))
    return note_keys


def save_notes_to_google_sheets(service_account_file, spreadsheet_id, worksheet_name, notes, progress_callback=None):
    client = _build_client(service_account_file)
    spreadsheet = client.open_by_key(spreadsheet_id)
    worksheet = _get_or_create_worksheet(spreadsheet, worksheet_name)
    _ensure_header_row(worksheet)
    existing_note_keys = _get_existing_note_keys(worksheet)

    rows_to_append = []
    for i, note in enumerate(tqdm(notes, desc="Sheets")):
        if progress_callback:
            progress_callback("sheets", i + 1, len(notes), note.get("title", ""))

        note_key = build_note_key_from_note(note)
        if not note_key[1] or note_key in existing_note_keys:
            continue

        rows_to_append.append(note_to_row(note))
        existing_note_keys.add(note_key)

    if not rows_to_append:
        return

    try:
        worksheet.append_rows(rows_to_append, value_input_option="RAW")
    except Exception as e:
        failed_count = len(rows_to_append)
        print(f"Failed to save notes to Google Sheets ({failed_count} rows): {e}")
