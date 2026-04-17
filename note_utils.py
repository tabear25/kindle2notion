from typing import Iterable


def normalize_text(value) -> str:
    return str(value or "").strip()


def build_note_key(title, content, page) -> tuple[str, str, str]:
    return (
        normalize_text(title),
        normalize_text(content),
        normalize_text(page),
    )


def build_note_key_from_note(note: dict) -> tuple[str, str, str]:
    return build_note_key(
        note.get("title", ""),
        note.get("content", ""),
        note.get("page", ""),
    )


def note_to_row(note: dict) -> list[str]:
    title, content, page = build_note_key_from_note(note)
    return [title, content, page]


def has_any_note_value(values: Iterable[str]) -> bool:
    return any(normalize_text(value) for value in values)
