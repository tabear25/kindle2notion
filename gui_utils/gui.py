import tkinter as tk
import tkinter.ttk as ttk
from typing import Callable, Optional, cast

WINDOW_BG = "#edf4ff"
CARD_BG = "#ffffff"
CARD_EDGE = "#d8e6f5"
HEADER_BG = "#f8fbff"
SURFACE_BG = "#f4f8fc"
TEXT_PRIMARY = "#0f172a"
TEXT_SECONDARY = "#475569"
TEXT_SUBTLE = "#64748b"
ACCENT = "#0ea5e9"
ACCENT_HOVER = "#0284c7"
ACCENT_SOFT = "#e0f2fe"
DANGER = "#dc2626"
DANGER_SOFT = "#fee2e2"
NEUTRAL_BORDER = "#cbd5e1"
SECONDARY_BG = "#eef4fb"
SECONDARY_HOVER = "#dbeafe"
SUCCESS = "#16a34a"
SUCCESS_SOFT = "#dcfce7"
BUTTON_TEXT = "#ffffff"
FONT_UI = "Yu Gothic UI"
FONT_CODE = "Consolas"
DONE_CLOSE_DELAY_MS = 200
_CANCELLED = object()

Validator = Callable[[str], Optional[str]]
Transformer = Callable[[str], object]


def _center_window(window: tk.Tk, width: int, height: int) -> None:
    window.update_idletasks()
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    x_position = max((screen_width - width) // 2, 40)
    y_position = max((screen_height - height) // 3, 40)
    window.geometry(f"{width}x{height}+{x_position}+{y_position}")


def _build_window(title: str, width: int, height: int) -> tk.Tk:
    root = tk.Tk()
    root.title(title)
    root.configure(bg=WINDOW_BG)
    root.resizable(False, False)
    root.attributes("-topmost", True)
    _center_window(root, width, height)
    return root


def _add_button_hover(button: tk.Button, normal_bg: str, hover_bg: str) -> None:
    button.bind("<Enter>", lambda _event: button.configure(bg=hover_bg))
    button.bind("<Leave>", lambda _event: button.configure(bg=normal_bg))


def _build_button(parent, text: str, command, bg: str, hover_bg: str, fg: str = BUTTON_TEXT) -> tk.Button:
    button = tk.Button(
        parent,
        text=text,
        command=command,
        bg=bg,
        fg=fg,
        activebackground=hover_bg,
        activeforeground=fg,
        relief="flat",
        bd=0,
        highlightthickness=0,
        font=(FONT_UI, 10, "bold"),
        padx=18,
        pady=11,
        cursor="hand2",
    )
    _add_button_hover(button, bg, hover_bg)
    return button


def _create_dialog(root: tk.Tk, badge_text: str, title: str, description: str) -> tk.Frame:
    shell = tk.Frame(root, bg=WINDOW_BG, padx=22, pady=22)
    shell.pack(fill="both", expand=True)

    border = tk.Frame(shell, bg=CARD_EDGE, padx=1, pady=1)
    border.pack(fill="both", expand=True)

    card = tk.Frame(border, bg=CARD_BG)
    card.pack(fill="both", expand=True)

    header = tk.Frame(card, bg=HEADER_BG, padx=24, pady=22)
    header.pack(fill="x")

    tk.Label(
        header,
        text=badge_text,
        bg=ACCENT_SOFT,
        fg=ACCENT_HOVER,
        font=(FONT_UI, 9, "bold"),
        padx=12,
        pady=4,
    ).pack(anchor="w")

    tk.Label(
        header,
        text=title,
        bg=HEADER_BG,
        fg=TEXT_PRIMARY,
        font=(FONT_UI, 18, "bold"),
        anchor="w",
    ).pack(anchor="w", pady=(16, 6))

    tk.Label(
        header,
        text=description,
        bg=HEADER_BG,
        fg=TEXT_SECONDARY,
        font=(FONT_UI, 10),
        anchor="w",
        justify="left",
        wraplength=420,
    ).pack(anchor="w")

    body = tk.Frame(card, bg=CARD_BG, padx=24, pady=22)
    body.pack(fill="both", expand=True)
    return body


def _show_input_dialog(
    *,
    window_title: str,
    badge_text: str,
    title: str,
    description: str,
    field_label: str,
    helper_text: str,
    submit_text: str,
    cancel_text: str,
    validator: Validator,
    transformer: Transformer,
    initial_value: str = "",
    width: int = 520,
    height: int = 360,
    entry_font: Optional[tuple] = None,
    entry_justify: str = "left",
) -> object:
    root = _build_window(window_title, width, height)
    body = _create_dialog(root, badge_text, title, description)

    tk.Label(
        body,
        text=field_label,
        bg=CARD_BG,
        fg=TEXT_PRIMARY,
        font=(FONT_UI, 10, "bold"),
        anchor="w",
    ).pack(fill="x")

    field_border = tk.Frame(body, bg=NEUTRAL_BORDER, padx=1, pady=1)
    field_border.pack(fill="x", pady=(10, 10))

    field_surface = tk.Frame(field_border, bg=SURFACE_BG, padx=14, pady=12)
    field_surface.pack(fill="both", expand=True)

    input_var = tk.StringVar(value=initial_value)
    entry = tk.Entry(
        field_surface,
        textvariable=input_var,
        relief="flat",
        bd=0,
        bg=SURFACE_BG,
        fg=TEXT_PRIMARY,
        insertbackground=ACCENT_HOVER,
        font=entry_font or (FONT_UI, 14),
        justify=entry_justify,
    )
    entry.pack(fill="x")

    helper_box = tk.Frame(body, bg=SECONDARY_BG, padx=12, pady=10)
    helper_box.pack(fill="x")
    tk.Label(
        helper_box,
        text=helper_text,
        bg=SECONDARY_BG,
        fg=TEXT_SUBTLE,
        font=(FONT_UI, 9),
        justify="left",
        anchor="w",
        wraplength=420,
    ).pack(fill="x")

    error_var = tk.StringVar(value="")
    tk.Label(
        body,
        textvariable=error_var,
        bg=CARD_BG,
        fg=DANGER,
        font=(FONT_UI, 9),
        anchor="w",
        justify="left",
        wraplength=420,
    ).pack(fill="x", pady=(12, 0))

    actions = tk.Frame(body, bg=CARD_BG)
    actions.pack(fill="x", pady=(18, 0))

    result = _CANCELLED

    def set_field_style(state: str = "default") -> None:
        if state == "error":
            field_border.configure(bg=DANGER)
            field_surface.configure(bg=DANGER_SOFT)
            entry.configure(bg=DANGER_SOFT)
            return

        border_color = ACCENT if entry.focus_get() == entry else NEUTRAL_BORDER
        field_border.configure(bg=border_color)
        field_surface.configure(bg=SURFACE_BG)
        entry.configure(bg=SURFACE_BG)

    def clear_error(_event=None) -> None:
        error_var.set("")
        set_field_style()

    def submit(_event=None):
        nonlocal result
        raw_value = input_var.get()
        error_message = validator(raw_value)
        if error_message:
            error_var.set(error_message)
            set_field_style("error")
            return "break"

        result = transformer(raw_value)
        root.destroy()
        return "break"

    def cancel(_event=None):
        root.destroy()
        return "break"

    cancel_button = _build_button(actions, cancel_text, cancel, SECONDARY_BG, SECONDARY_HOVER, TEXT_PRIMARY)
    cancel_button.pack(side="left")

    submit_button = _build_button(actions, submit_text, submit, ACCENT, ACCENT_HOVER)
    submit_button.pack(side="right")

    entry.bind("<Return>", submit)
    entry.bind("<Escape>", cancel)
    entry.bind("<KeyRelease>", clear_error)
    entry.bind("<FocusIn>", lambda _event: set_field_style())
    entry.bind("<FocusOut>", lambda _event: set_field_style())
    root.bind("<Escape>", cancel)
    root.protocol("WM_DELETE_WINDOW", cancel)

    root.after(80, lambda: entry.focus_force())
    if initial_value:
        root.after(100, lambda: entry.select_range(0, tk.END))

    set_field_style()
    root.mainloop()
    return result


def _show_message_dialog(
    *,
    window_title: str,
    badge_text: str,
    title: str,
    description: str,
    button_text: str,
    width: int = 460,
    height: int = 280,
) -> None:
    root = _build_window(window_title, width, height)
    body = _create_dialog(root, badge_text, title, description)

    close_button = _build_button(body, button_text, root.destroy, ACCENT, ACCENT_HOVER)
    close_button.pack(side="right")

    root.bind("<Return>", lambda _event: root.destroy())
    root.bind("<Escape>", lambda _event: root.destroy())
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.after(80, close_button.focus_force)
    root.mainloop()


class ProgressWindow:
    _PHASES = [
        ("scrape", "ハイライト取得"),
        ("notion", "Notion 保存"),
        ("sheets", "Google Sheets 保存"),
    ]

    def __init__(self, total_books: Optional[int] = None) -> None:
        del total_books
        self._root = _build_window("同期中", 520, 460)

        style = ttk.Style(self._root)
        style.theme_use("default")
        style.configure(
            "Accent.Horizontal.TProgressbar",
            troughcolor=SECONDARY_BG,
            background=ACCENT,
            thickness=10,
        )

        shell = tk.Frame(self._root, bg=WINDOW_BG, padx=22, pady=22)
        shell.pack(fill="both", expand=True)

        border = tk.Frame(shell, bg=CARD_EDGE, padx=1, pady=1)
        border.pack(fill="both", expand=True)

        card = tk.Frame(border, bg=CARD_BG)
        card.pack(fill="both", expand=True)

        header = tk.Frame(card, bg=HEADER_BG, padx=24, pady=18)
        header.pack(fill="x")

        tk.Label(
            header,
            text="SYNC IN PROGRESS",
            bg=ACCENT_SOFT,
            fg=ACCENT_HOVER,
            font=(FONT_UI, 9, "bold"),
            padx=12,
            pady=4,
        ).pack(anchor="w")

        tk.Label(
            header,
            text="Kindle ハイライトを同期しています",
            bg=HEADER_BG,
            fg=TEXT_PRIMARY,
            font=(FONT_UI, 16, "bold"),
            anchor="w",
        ).pack(anchor="w", pady=(14, 4))

        tk.Label(
            header,
            text="現在の進行状況をリアルタイムで表示しています。",
            bg=HEADER_BG,
            fg=TEXT_SECONDARY,
            font=(FONT_UI, 10),
            anchor="w",
        ).pack(anchor="w")

        body = tk.Frame(card, bg=CARD_BG, padx=24, pady=16)
        body.pack(fill="both", expand=True)

        self._bars = {}
        self._count_vars = {}
        self._status_vars = {}

        for key, label in self._PHASES:
            self._build_phase_row(body, key, label)

        tk.Frame(card, bg=CARD_EDGE, height=1).pack(fill="x")

        self._status_bar_frame = tk.Frame(card, bg=SECONDARY_BG, padx=24, pady=14)
        self._status_bar_frame.pack(fill="x")

        self._status_bar_var = tk.StringVar(value="ログインを待っています...")
        self._status_bar_label = tk.Label(
            self._status_bar_frame,
            textvariable=self._status_bar_var,
            bg=SECONDARY_BG,
            fg=TEXT_SECONDARY,
            font=(FONT_UI, 10),
            anchor="w",
        )
        self._status_bar_label.pack(side="left", fill="x", expand=True)

        self._close_button = None
        self._root.protocol("WM_DELETE_WINDOW", lambda: None)

    def _build_phase_row(self, parent: tk.Frame, key: str, label: str) -> None:
        row = tk.Frame(parent, bg=CARD_BG)
        row.pack(fill="x", pady=(0, 12))

        top = tk.Frame(row, bg=CARD_BG)
        top.pack(fill="x")

        tk.Label(
            top,
            text=label,
            bg=CARD_BG,
            fg=TEXT_PRIMARY,
            font=(FONT_UI, 10, "bold"),
            anchor="w",
        ).pack(side="left")

        count_var = tk.StringVar(value="")
        tk.Label(
            top,
            textvariable=count_var,
            bg=CARD_BG,
            fg=TEXT_SUBTLE,
            font=(FONT_UI, 9),
            anchor="e",
        ).pack(side="right")
        self._count_vars[key] = count_var

        bar = ttk.Progressbar(
            row,
            orient="horizontal",
            mode="determinate",
            style="Accent.Horizontal.TProgressbar",
        )
        bar.pack(fill="x", pady=(6, 4))
        self._bars[key] = bar

        status_var = tk.StringVar(value="")
        tk.Label(
            row,
            textvariable=status_var,
            bg=CARD_BG,
            fg=TEXT_SUBTLE,
            font=(FONT_UI, 9),
            anchor="w",
            wraplength=440,
        ).pack(fill="x")
        self._status_vars[key] = status_var

    def update(self, phase: str, current: int, total: int, message: str) -> None:
        self._root.after(0, lambda: self._apply(phase, current, total, message))

    def mark_done(self) -> None:
        self._root.after(0, self._show_done)

    def mark_error(self, message: str) -> None:
        self._root.after(0, lambda: self._show_error(message))

    def run(self) -> None:
        self._root.mainloop()

    def _apply(self, phase: str, current: int, total: int, message: str) -> None:
        if phase not in self._bars:
            return

        if total > 0:
            self._bars[phase]["value"] = (current / total) * 100
            self._count_vars[phase].set(f"{current} / {total}")

        self._status_vars[phase].set(message)
        self._status_bar_var.set(message)

    def _show_done(self) -> None:
        for bar in self._bars.values():
            bar["value"] = 100

        self._status_bar_frame.configure(bg=SUCCESS_SOFT)
        self._status_bar_label.configure(bg=SUCCESS_SOFT, fg=SUCCESS)
        self._status_bar_var.set("同期が完了しました")
        self._root.protocol("WM_DELETE_WINDOW", self._root.destroy)
        self._root.after(DONE_CLOSE_DELAY_MS, self._root.destroy)

    def _show_error(self, message: str) -> None:
        self._status_bar_frame.configure(bg=DANGER_SOFT)
        self._status_bar_label.configure(bg=DANGER_SOFT, fg=DANGER)
        self._status_bar_var.set(f"エラー: {message}")
        self._ensure_close_button()
        self._root.protocol("WM_DELETE_WINDOW", self._root.destroy)

    def _ensure_close_button(self) -> None:
        if self._close_button is not None:
            return

        self._close_button = _build_button(
            self._status_bar_frame,
            "閉じる",
            self._root.destroy,
            ACCENT,
            ACCENT_HOVER,
        )
        self._close_button.pack(side="right")


def show_popup_message(message: str, title: str = "処理結果") -> None:
    _show_message_dialog(
        window_title=title,
        badge_text="NOTIFICATION",
        title=title,
        description=message,
        button_text="閉じる",
    )


def ask_book_limit(default: Optional[int] = None) -> Optional[int]:
    def validate(value: str) -> Optional[str]:
        text = value.strip()
        if text == "":
            return None
        if text.isdigit() and int(text) > 0:
            return None
        return "1 以上の整数を入力してください。空欄のままなら全件取得します。"

    result = _show_input_dialog(
        window_title="取得する冊数を設定",
        badge_text="SCRAPE SETUP",
        title="取得する書籍数を決めます",
        description="冊数を指定すると、その件数までを対象に処理します。空欄なら表示中のすべてを取得します。",
        field_label="取得する書籍数",
        helper_text="空欄のまま開始すると、表示されているすべての書籍を対象に処理します。",
        submit_text="この条件で開始",
        cancel_text="キャンセル",
        validator=validate,
        transformer=lambda value: None if value.strip() == "" else int(value.strip()),
        initial_value="" if default is None else str(default),
    )
    if result is _CANCELLED:
        raise SystemExit("Cancelled by user.")
    return cast(Optional[int], result)


def prompt_two_factor_code() -> Optional[str]:
    def validate(value: str) -> Optional[str]:
        code = value.strip().replace(" ", "")
        if not code:
            return "確認コードを入力してください。"
        if len(code) < 4:
            return "Amazon から届いた確認コードをそのまま入力してください。"
        return None

    result = _show_input_dialog(
        window_title="2段階認証",
        badge_text="SECURITY CHECK",
        title="Amazon の確認コードを入力してください",
        description="ログインを続行するために、メールや認証アプリに表示されたコードが必要です。",
        field_label="確認コード",
        helper_text="入力後に送信すると、ログイン処理を再開します。",
        submit_text="コードを送信",
        cancel_text="中止",
        validator=validate,
        transformer=lambda value: value.strip().replace(" ", ""),
        width=460,
        height=350,
        entry_font=(FONT_CODE, 18, "bold"),
        entry_justify="center",
    )
    if result is _CANCELLED:
        return None
    return cast(str, result)
