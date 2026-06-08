"""Add highlights for non-Kindle / physical books to Notion + Google Sheets.

The Kindle scraper (``main.py``) can only reach books bought on Amazon Kindle.
This script is the companion path for everything else -- paper books, PDFs,
library loans, e-books from other stores -- so their highlights land in exactly
the same Notion database and Google Sheets v2 schema as the scraped ones.

It is meant to be driven by an AI assistant (e.g. Claude Code): the assistant
collects the book title + highlights from the user, writes them to a small JSON
file, and runs this script. It can also be run by hand.

Input formats (any one of):

* ``--input book.json``   -- read a JSON payload from a file
* ``--stdin``             -- read the same JSON payload from standard input
* ``--title`` + ``--highlight`` (repeatable) -- quick single-book entry

JSON payload (``books`` may be omitted for a single book)::

    {
      "books": [
        {
          "title": "ファスト&スロー",          // required
          "author": "ダニエル・カーネマン",      // optional book metadata ...
          "genre": "behavioral economics",
          "reading_status": "読了",
          "finished_at": "2026-05-30",
          "rating": "5",
          "source": "physical",                 // default: "manual"
          "highlights": [                        // required, non-empty
            {"content": "ハイライト本文", "page": "42"},
            {"content": "別の本文", "location": "1200-1210"},
            "本文だけの文字列でもOK"
          ]
        }
      ]
    }

Usage::

    python -m scripts.add_manual_highlights --input book.json            # dry-run
    python -m scripts.add_manual_highlights --input book.json --apply     # write
    python -m scripts.add_manual_highlights --stdin --apply --sheets-only

    # Read-only: list existing books, optionally ranked against a typed title,
    # so the assistant can catch a typo before it creates a duplicate book.
    python -m scripts.add_manual_highlights --list-books
    python -m scripts.add_manual_highlights --list-books --title "ファストアンドスロー"

Dedup is handled by the existing Notion / Sheets writers, so re-running with the
same content is safe -- duplicates are skipped, not re-added. A highlight merges
into an existing book only when its ``title`` matches that book's title exactly
(book_id is derived from the raw title). Because of that, a typo'd title silently
creates a *separate* book -- so the intended flow is: assistant runs
``--list-books --title "<user input>"``, reconciles against the returned matches
(see :func:`find_similar_titles`), confirms the canonical title with the user,
and only then adds the highlights under that exact title.
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
import unicodedata
from pathlib import Path

# Make the project root importable when run as ``python scripts/...``.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from note_utils import (  # noqa: E402  (needs path insert)
    BOOK_META_KEYS,
    normalize_text,
    stable_book_id,
)

DEFAULT_SOURCE = "manual"

# Keys copied verbatim from each highlight entry into the note dict.
_HIGHLIGHT_PASSTHROUGH = ("page", "location", "highlighted_at")

# Default similarity threshold for fuzzy title matching (difflib ratio, 0..1).
DEFAULT_MATCH_CUTOFF = 0.6


class SheetsNotConfigured(RuntimeError):
    """Raised by an operation that needs Google Sheets when it isn't configured.

    The CLI turns this into a ``SystemExit`` (clean message, no traceback); the
    web API turns it into a ``sheets_configured: false`` JSON response so a
    phone / assistant caller can fall back gracefully.
    """


# ---------------------------------------------------------------------------
# Pure helpers (no network / heavy deps) -- unit-tested in test/.
# ---------------------------------------------------------------------------


def normalize_title_for_match(title: str) -> str:
    """Aggressively normalise a title for *fuzzy comparison only*.

    This is NOT the stored title and never feeds ``stable_book_id`` -- it exists
    purely so two near-identical titles compare as similar. It applies Unicode
    NFKC (folds full-width <-> half-width and many compatibility forms), lower-
    cases, drops all whitespace, and strips common punctuation/symbols that users
    type inconsistently (``&`` vs ``＆`` vs ``アンド``, middots, brackets, etc.).
    """
    text = unicodedata.normalize("NFKC", title or "")
    text = text.lower()
    # Remove whitespace entirely so word-spacing differences don't matter.
    text = "".join(text.split())
    # Drop punctuation/symbol characters that are typed inconsistently.
    text = "".join(ch for ch in text if not unicodedata.category(ch).startswith("P")
                   and not unicodedata.category(ch).startswith("S"))
    return text


def find_similar_titles(
    target: str,
    candidates,
    *,
    limit: int = 5,
    cutoff: float = DEFAULT_MATCH_CUTOFF,
) -> list[tuple[str, float]]:
    """Return ``[(candidate_title, score), ...]`` ranked by similarity to ``target``.

    Scores are difflib ratios (0..1) computed on the *normalised* forms (see
    :func:`normalize_title_for_match`), so full/half-width and spacing variants
    score high. Only candidates with ``score >= cutoff`` are returned, best
    first, capped at ``limit``. A normalised-exact match always scores ``1.0``.
    This is a deterministic safety net; the driving assistant is expected to
    apply its own judgement on top (Japanese kana/kanji variants in particular).
    """
    norm_target = normalize_title_for_match(target)
    # A degenerate query that normalises to nothing (all whitespace / punctuation
    # / symbols) carries no signal: bail out rather than let difflib score it
    # against an equally-degenerate candidate at a spurious 1.0.
    if not norm_target:
        return []
    scored: list[tuple[str, float]] = []
    for candidate in candidates:
        norm_candidate = normalize_title_for_match(candidate)
        if not norm_candidate:
            # Candidate has no comparable content; skip so it can never score
            # 1.0 against a (now non-empty) target.
            continue
        if norm_target == norm_candidate:
            score = 1.0
        else:
            score = difflib.SequenceMatcher(None, norm_target, norm_candidate).ratio()
        scored.append((candidate, round(score, 4)))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [(title, score) for title, score in scored if score >= cutoff][:limit]


def _coerce_books(payload) -> list:
    """Return the list of book dicts from a flexible payload shape."""
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object or array")
    if "books" in payload:
        books = payload["books"]
        if not isinstance(books, list):
            raise ValueError("'books' must be an array")
        return books
    # Single-book shorthand: the payload *is* one book.
    if "title" in payload or "highlights" in payload:
        return [payload]
    raise ValueError(
        "payload must contain a 'books' array or a single book with "
        "'title' / 'highlights'"
    )


def _coerce_highlight(highlight) -> dict:
    """Allow each highlight to be a bare string or a full object."""
    if isinstance(highlight, str):
        return {"content": highlight}
    if isinstance(highlight, dict):
        return highlight
    raise ValueError(
        f"each highlight must be a string or object, got {type(highlight).__name__}"
    )


def build_notes_from_payload(payload, default_source: str = DEFAULT_SOURCE) -> list[dict]:
    """Convert a payload into the project's shared note-dict list.

    Raises ``ValueError`` on a missing title, an empty highlight list, or an
    empty highlight content -- callers should surface the message to the user.
    """
    books = _coerce_books(payload)
    if not books:
        raise ValueError("payload contains no books")

    notes: list[dict] = []
    for b_index, book in enumerate(books):
        if not isinstance(book, dict):
            raise ValueError(f"book #{b_index + 1} must be an object")

        title = normalize_text(book.get("title"))
        if not title:
            raise ValueError(f"book #{b_index + 1} is missing a non-empty 'title'")

        raw_highlights = book.get("highlights")
        if not isinstance(raw_highlights, list) or not raw_highlights:
            raise ValueError(f"book '{title}' has no highlights")

        book_source = normalize_text(book.get("source")) or default_source
        book_meta = {
            key: normalize_text(book.get(key, ""))
            for key in BOOK_META_KEYS
            if normalize_text(book.get(key, ""))
        }

        for h_index, raw in enumerate(raw_highlights):
            highlight = _coerce_highlight(raw)
            content = normalize_text(highlight.get("content"))
            if not content:
                raise ValueError(
                    f"book '{title}' highlight #{h_index + 1} has empty 'content'"
                )

            note = {
                "title": title,
                "content": content,
                "source": normalize_text(highlight.get("source")) or book_source,
            }
            for key in _HIGHLIGHT_PASSTHROUGH:
                note[key] = normalize_text(highlight.get(key, ""))
            note.update(book_meta)
            notes.append(note)

    return notes


def summarize_plan(notes: list[dict]) -> list[tuple[str, int, str]]:
    """Group notes into ``(title, highlight_count, source)`` rows, in order."""
    order: list[str] = []
    counts: dict[str, int] = {}
    sources: dict[str, str] = {}
    for note in notes:
        title = note["title"]
        if title not in counts:
            order.append(title)
            counts[title] = 0
            sources[title] = note.get("source", DEFAULT_SOURCE)
        counts[title] += 1
    return [(title, counts[title], sources[title]) for title in order]


# ---------------------------------------------------------------------------
# Reusable operations (shared by the CLI and the web API)
#
# These carry the actual side effects -- reading Google Sheets, writing to
# Notion / Sheets -- but return plain data instead of printing, so both the CLI
# (``main_cli`` / ``_run_list_books``) and ``web/app.py`` can drive them without
# duplicating logic. Heavy deps (``main``, ``notion``, ``gspread``) are still
# imported lazily inside, so importing this module stays cheap.
# ---------------------------------------------------------------------------


def build_books_result(
    title: str | None = None,
    *,
    match_cutoff: float = DEFAULT_MATCH_CUTOFF,
    matches_only: bool = False,
) -> dict:
    """Return the existing-books result (the same dict ``--list-books`` prints).

    Read-only: loads config and reads ``01_books`` via
    :func:`toSheets.list_existing_books`, never writing. When ``title`` is given,
    adds ``matches_for_title`` -- the existing titles most similar to it (see
    :func:`find_similar_titles`) so a typo'd title surfaces the real book to
    merge into. ``matches_only`` omits the (potentially large) full ``books``
    list and is only meaningful together with ``title``.

    Raises :class:`SheetsNotConfigured` when Google Sheets is not set up.
    """
    import main  # noqa: E402

    main.load_config()
    if not main.GOOGLE_SHEETS_ENABLED:
        raise SheetsNotConfigured(
            "Google Sheets is not configured. Set "
            "GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE and GOOGLE_SHEETS_SPREADSHEET_ID "
            "in config/KEYS.env."
        )

    from google_sheets import toSheets  # noqa: E402

    books = toSheets.list_existing_books(
        main.GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE, main.GOOGLE_SHEETS_SPREADSHEET_ID
    )
    result: dict = {"count": len(books)}

    if title:
        titles = [b["title"] for b in books]
        ranked = find_similar_titles(title, titles, cutoff=match_cutoff)
        by_title = {b["title"]: b for b in books}
        # is_exact_normalized comes from REAL normalized equality, not the
        # rounded score: a near-identical (non-equal) pair can round to 1.0, and
        # the SKILL uses this flag to skip user confirmation.
        norm_query = normalize_title_for_match(title)
        result["query_title"] = title
        result["matches_for_title"] = [
            {
                "title": match_title,
                "score": score,
                "book_id": by_title[match_title]["book_id"],
                "is_exact_normalized": normalize_title_for_match(match_title) == norm_query,
            }
            for match_title, score in ranked
        ]

    # The full book list can be large; omit it when the caller only wants the
    # ranked matches for a query title. Without --title there is nothing to
    # rank, so the full list is always included.
    if not (matches_only and title):
        result["books"] = books

    return result


def write_notes(notes: list[dict], targets: list[str], *, apply: bool = True) -> dict:
    """Write ``notes`` to the given ``targets`` ("Notion" / "Google Sheets").

    Returns ``{"notion", "sheets", "problems"}`` where each destination value is
    that writer's summary dict, ``{"not_configured": True}`` (Sheets targeted but
    unset), or ``None`` (not targeted / dry-run). ``problems`` collects
    human-readable strings for anything that did not get written cleanly, so the
    caller can refuse to report a partial failure as success. A no-op returning
    empty results when ``apply`` is False (callers do their own dry-run plan).
    """
    result: dict = {"notion": None, "sheets": None, "problems": []}
    if not apply:
        return result

    import main  # noqa: E402

    main.load_config()

    if "Notion" in targets:
        from notion import toNotion  # noqa: E402

        summary = toNotion.save_notes_to_notion(
            main.NOTION_API_KEY, main.NOTION_DATABASE_ID, notes
        )
        result["notion"] = summary
        if summary["failed"]:
            result["problems"].append(f"{summary['failed']} Notion write(s) failed")

    if "Google Sheets" in targets:
        if not main.GOOGLE_SHEETS_ENABLED:
            result["sheets"] = {"not_configured": True}
        else:
            from google_sheets import toSheets  # noqa: E402

            summary = toSheets.save_notes_to_google_sheets(
                main.GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE,
                main.GOOGLE_SHEETS_SPREADSHEET_ID,
                notes,
            )
            result["sheets"] = summary
            if summary["skipped_invalid"]:
                result["problems"].append(
                    f"{summary['skipped_invalid']} Sheets row(s) dropped "
                    "(empty title/content)"
                )

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _ratio_float(value: str) -> float:
    """argparse type: a float in the inclusive range 0..1.

    Rejects out-of-range values up front so ``--match-cutoff`` can't silently
    misbehave (a cutoff > 1.0 would drop even an exact match; a negative cutoff
    would return everything). Raises ``argparse.ArgumentTypeError`` otherwise.
    """
    try:
        parsed = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not a number")
    if not (0.0 <= parsed <= 1.0):
        raise argparse.ArgumentTypeError(
            f"must be between 0 and 1 (inclusive), got {parsed}"
        )
    return parsed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Add non-Kindle / physical book highlights to Notion + Sheets."
    )
    src = parser.add_argument_group("input (choose one)")
    src.add_argument("--input", help="path to a JSON payload file")
    src.add_argument("--stdin", action="store_true", help="read JSON payload from stdin")
    src.add_argument("--title", help="quick mode: single book title")
    src.add_argument(
        "--highlight",
        action="append",
        metavar="TEXT",
        help="quick mode: a highlight body (repeatable; use JSON for page/location)",
    )
    src.add_argument("--author", help="quick mode: book author")
    src.add_argument(
        "--source",
        help=f"quick mode: source label for the highlights (default: {DEFAULT_SOURCE!r})",
    )

    parser.add_argument(
        "--list-books",
        action="store_true",
        help="read-only: print existing books (JSON) from Google Sheets 01_books "
        "and exit. Use this to fuzzy-match a user title against titles already on "
        "record before adding, so typos don't create a duplicate book.",
    )
    parser.add_argument(
        "--match-cutoff",
        type=_ratio_float,
        default=DEFAULT_MATCH_CUTOFF,
        metavar="0..1",
        help=f"similarity cutoff for --list-books matching, 0..1 (default: {DEFAULT_MATCH_CUTOFF})",
    )
    parser.add_argument(
        "--matches-only",
        action="store_true",
        help="with --list-books --title: omit the full book list, return only the "
        "ranked matches (compact output for the assistant). Without --title it is ignored.",
    )

    parser.add_argument("--apply", action="store_true", help="actually write (default: dry-run)")
    dest = parser.add_mutually_exclusive_group()
    dest.add_argument("--notion-only", action="store_true", help="write only to Notion")
    dest.add_argument("--sheets-only", action="store_true", help="write only to Google Sheets")
    return parser


def _selected_input_sources(args) -> list[str]:
    """Names of the input sources the user actually supplied (0, 1, or more)."""
    selected = []
    if args.input:
        selected.append("--input")
    if args.stdin:
        selected.append("--stdin")
    if args.title:
        selected.append("--title")
    return selected


def _validate_input_sources(parser, args) -> None:
    """Reject 0 or >1 input sources with a clear argparse error (exit code 2)."""
    selected = _selected_input_sources(args)
    if not selected:
        parser.error(
            "no input source: provide one of --input <file>, --stdin, "
            "or --title (with --highlight)."
        )
    if len(selected) > 1:
        parser.error(
            f"choose only one input source, got {', '.join(selected)}."
        )


def _payload_from_args(args) -> object:
    """Load the JSON payload from the single selected input source.

    Assumes ``_validate_input_sources`` already ran, so exactly one of
    ``--input`` / ``--stdin`` / ``--title`` is set. Bad files / malformed JSON /
    an interactive ``--stdin`` with nothing piped raise ``SystemExit`` with a
    clear message instead of an uncaught traceback or an indefinite hang.
    """
    if args.input:
        try:
            # utf-8-sig transparently strips a UTF-8 BOM, which Windows editors
            # and PowerShell's ``Out-File -Encoding utf8`` prepend; plain utf-8
            # would choke on it.
            with open(args.input, encoding="utf-8-sig") as fh:
                return json.load(fh)
        except (FileNotFoundError, OSError) as exc:
            raise SystemExit(f"Cannot read --input file {args.input!r}: {exc}")
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Invalid JSON in --input file {args.input!r}: {exc}")
    if args.stdin:
        if sys.stdin.isatty():
            raise SystemExit(
                "--stdin given but no data is piped in (stdin is a terminal). "
                "Pipe a JSON payload, or use --input <file>."
            )
        try:
            return json.load(sys.stdin)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Invalid JSON on stdin: {exc}")
    # Quick mode (--title): validated above, so args.title is set.
    book: dict = {"title": args.title}
    if args.author:
        book["author"] = args.author
    if args.source:
        book["source"] = args.source
    book["highlights"] = list(args.highlight or [])
    return {"books": [book]}


def _resolve_targets(args) -> list[str]:
    if args.notion_only:
        return ["Notion"]
    if args.sheets_only:
        return ["Google Sheets"]
    return ["Notion", "Google Sheets"]


def _run_list_books(args) -> int:
    """Print existing books (JSON) so the assistant can fuzzy-match titles.

    Read-only: never writes. Emits a JSON object on stdout::

        {"count": N, "books": [{"book_id", "title", "author", "highlight_count"}, ...]}

    If ``--title`` is also given, adds ``"matches_for_title"`` -- the existing
    titles most similar to it (difflib over NFKC-normalised forms), so a typo'd
    title surfaces the real book to merge into. The actual work lives in
    :func:`build_books_result` (shared with the web API); here we just print it
    and turn :class:`SheetsNotConfigured` into a clean ``SystemExit``.
    """
    try:
        result = build_books_result(
            args.title, match_cutoff=args.match_cutoff, matches_only=args.matches_only
        )
    except SheetsNotConfigured as exc:
        raise SystemExit(str(exc))

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main_cli(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Read-only listing mode: standalone, takes no payload. Runs before input-
    # source validation so it can be combined with a bare --title (used as the
    # fuzzy-match query) without requiring --highlight.
    if args.list_books:
        return _run_list_books(args)

    _validate_input_sources(parser, args)

    payload = _payload_from_args(args)
    try:
        notes = build_notes_from_payload(payload)
    except ValueError as exc:
        raise SystemExit(f"Invalid input: {exc}")

    plan = summarize_plan(notes)
    targets = _resolve_targets(args)
    print(f"[plan] {len(plan)} book(s), {len(notes)} highlight(s) -> {' + '.join(targets)}:")
    for title, count, source in plan:
        print(f"  - {title}  ({count} highlight(s), source={source})")

    if not args.apply:
        print(
            "\n(dry-run) Nothing written. Re-run with --apply to write to "
            f"{' + '.join(targets)}."
        )
        return 0

    # Heavy imports are deferred (inside write_notes) so the pure helpers above
    # stay importable (and unit-testable) without playwright / notion / gspread.
    result = write_notes(notes, targets, apply=True)

    if result["notion"] is not None:
        summary = result["notion"]
        print(
            f"[Notion] added {summary['added']}, "
            f"skipped {summary['skipped']} (already present), "
            f"failed {summary['failed']}"
        )

    if result["sheets"] is not None:
        summary = result["sheets"]
        if summary.get("not_configured"):
            print("[Google Sheets] not configured (skipped). "
                  "Set GOOGLE_SHEETS_* in config/KEYS.env to enable.")
        else:
            print(
                f"[Google Sheets] new books {summary['new_books']}, "
                f"new highlights {summary['new_highlights']}, "
                f"skipped {summary['skipped_duplicates']} (already present), "
                f"dropped {summary['skipped_invalid']} (empty title/content)"
            )

    if result["problems"]:
        print("\n[partial failure] " + "; ".join(result["problems"]))
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main_cli())
