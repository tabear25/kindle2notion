"""Write Kindle highlights to per-book Markdown files under ``highlights/``.

One ``.md`` file is created per book. Re-runs append only new highlights;
existing ones (identified by a ``<!-- HL-... -->`` marker and the content
dedup key) are kept untouched. The header's ``last_synced_at`` is refreshed
on every run that touches the book.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from tqdm import tqdm

from note_utils import (
    content_dedup_key,
    highlight_id,
    normalize_text,
    stable_book_id,
    today_iso,
)

DEFAULT_OUTPUT_DIRNAME = "highlights"

_INVALID_FS_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t]+')
_HL_MARKER_RE = re.compile(r"<!--\s*(HL-[A-Z0-9]+-\d+)\s*-->")
_FIRST_SYNCED_RE = re.compile(r"^- first_synced_at:\s*(\S+)\s*$", re.MULTILINE)
_HEADER_SEPARATOR_RE = re.compile(r"^---\s*$", re.MULTILINE)


def _sanitize_filename(title: str, fallback: str) -> str:
    cleaned = _INVALID_FS_CHARS.sub("_", title or "").strip().strip(".")
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        cleaned = fallback
    return cleaned[:120]


def _parse_existing(path: Path, book_id: str) -> tuple[set, int, str]:
    """Return ``(dedup_keys, max_idx, first_synced_at)`` for an existing file."""
    if not path.exists():
        return set(), 0, ""

    text = path.read_text(encoding="utf-8")

    first_synced = ""
    m = _FIRST_SYNCED_RE.search(text)
    if m:
        first_synced = m.group(1)

    dedup: set = set()
    max_idx = 0

    entries = re.split(r"(?=<!--\s*HL-)", text)
    for entry in entries:
        hl_match = _HL_MARKER_RE.search(entry)
        if not hl_match:
            continue
        hid = hl_match.group(1)
        tail = hid.rsplit("-", 1)[-1]
        if tail.isdigit():
            idx = int(tail)
            if idx > max_idx:
                max_idx = idx

        content_lines: list[str] = []
        started = False
        for line in entry.splitlines():
            if line.startswith(">"):
                content_lines.append(line[1:].lstrip() if line.startswith("> ") is False else line[2:])
                started = True
            elif started:
                break
        if content_lines:
            content = "\n".join(content_lines).strip()
            if content:
                dedup.add(content_dedup_key(book_id, content))

    return dedup, max_idx, first_synced


def _render_header(title: str, book_id: str, first_synced: str, last_synced: str) -> str:
    return (
        f"# {title}\n\n"
        f"- book_id: {book_id}\n"
        f"- first_synced_at: {first_synced}\n"
        f"- last_synced_at: {last_synced}\n\n"
        f"---\n\n"
    )


def _render_entry(hid: str, note: dict, synced_at: str) -> str:
    content = normalize_text(note.get("content", ""))
    quoted = "\n".join(f"> {line}" if line else ">" for line in content.splitlines())
    location = normalize_text(note.get("location") or note.get("page", ""))
    highlighted_at = normalize_text(note.get("highlighted_at", ""))

    lines = [f"<!-- {hid} -->", quoted, ""]
    if location:
        lines.append(f"- location: {location}")
    if highlighted_at:
        lines.append(f"- highlighted_at: {highlighted_at}")
    lines.append(f"- synced_at: {synced_at}")
    lines.append("")
    return "\n".join(lines) + "\n"


def _strip_header(text: str) -> str:
    """Return the body of an existing file (everything past the first ``---``)."""
    sep_match = _HEADER_SEPARATOR_RE.search(text)
    if not sep_match:
        return text
    body = text[sep_match.end():]
    return body.lstrip("\n")


def save_notes_to_local_markdown(
    output_dir,
    notes: Iterable,
    progress_callback=None,
):
    """Write/append per-book Markdown files into ``output_dir``."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    grouped: dict = {}
    for note in notes:
        title = normalize_text(note.get("title", ""))
        content = normalize_text(note.get("content", ""))
        if not title or not content:
            continue
        bid = note.get("book_id") or stable_book_id(title)
        slot = grouped.setdefault(bid, {"title": title, "notes": []})
        slot["notes"].append(note)

    today = today_iso()
    total = len(grouped)

    for i, (bid, info) in enumerate(tqdm(grouped.items(), desc="Local")):
        title = info["title"]
        if progress_callback:
            progress_callback("local", i + 1, total, title)

        filename = _sanitize_filename(title, fallback=bid) + ".md"
        path = output_path / filename

        dedup, max_idx, first_synced = _parse_existing(path, bid)
        if not first_synced:
            first_synced = today

        new_entries: list[str] = []
        for note in info["notes"]:
            content = normalize_text(note.get("content", ""))
            key = content_dedup_key(bid, content)
            if key in dedup:
                continue

            max_idx += 1
            supplied_idx = note.get("idx_within_book")
            if isinstance(supplied_idx, int) and supplied_idx > max_idx:
                max_idx = supplied_idx

            hid = highlight_id(bid, max_idx)
            new_entries.append(_render_entry(hid, note, today))
            dedup.add(key)

        if path.exists():
            existing = path.read_text(encoding="utf-8")
            body = _strip_header(existing)
            file_text = _render_header(title, bid, first_synced, today) + body
            if new_entries:
                if not file_text.endswith("\n"):
                    file_text += "\n"
                file_text += "".join(new_entries)
        else:
            file_text = _render_header(title, bid, first_synced, today) + "".join(new_entries)

        path.write_text(file_text, encoding="utf-8")
