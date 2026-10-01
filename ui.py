import threading
import tkinter as tk

import customtkinter as ctk

import history as history_store
from config import (
    ACTIONS,
    PROVIDER_LABELS,
    PROVIDER_URLS,
    SUMMARIZE_PRESETS,
    TONES,
    TRANSLATE_LANG_GROUPS,
    TRANSLATE_LANGS,
    VERSION,
    API_KEYS,
    action_label,
    get,
    load_settings,
    reload_api_keys,
    save_settings,
)
from textdiff import diff_spans, has_changes, preview_spans

# Modern palette
ACCENT = "#4f8cff"
ACCENT_SOFT = "#1a2744"
SUCCESS = "#3ddc97"
DANGER = "#ff6b6b"
WARNING = "#feca57"
SIDEBAR_BG = "#0b1220"
SIDEBAR_HOVER = "#162036"
CARD_DARK = "#111a2e"
CARD_LIGHT = "#f7f8fa"
TEXT_MUTED_DARK = "#7d8aa3"
TEXT_MUTED_LIGHT = "#5c6577"
BORDER_DARK = "#1e2a42"
BORDER_LIGHT = "#e6e9ef"

THEME = "dark"


def palette():
    dark = THEME == "dark"
    return {
        "bg": "#0b1220" if dark else "#f4f6fb",
        "card": CARD_DARK if dark else "#ffffff",
        "card2": "#0f1729" if dark else "#f0f2f7",
        "text": "#e8edf7" if dark else "#152038",
        "muted": TEXT_MUTED_DARK if dark else TEXT_MUTED_LIGHT,
        "border": BORDER_DARK if dark else BORDER_LIGHT,
        "sidebar": SIDEBAR_BG if dark else "#101828",
        "sidebar_hover": SIDEBAR_HOVER if dark else "#1a2438",
        "sidebar_text": "#c5d0e4" if dark else "#d5deef",
        "sidebar_active": ACCENT,
    }


def apply_theme(theme: str | None = None) -> None:
    global THEME
    THEME = "dark"
    ctk.set_appearance_mode("dark")


class Card(ctk.CTkFrame):
    def __init__(self, master, **kw):
        p = palette()
        kw.setdefault("corner_radius", 14)
        kw.setdefault("fg_color", p["card"])
        kw.setdefault("border_width", 1)
        kw.setdefault("border_color", p["border"])
        super().__init__(master, **kw)


def section_title(parent, text, sub=""):
    p = palette()
    wrap = ctk.CTkFrame(parent, fg_color="transparent")
    wrap.pack(fill="x", pady=(0, 14))
    ctk.CTkLabel(wrap, text=text, font=("Segoe UI Semibold", 22), text_color=p["text"]).pack(
        anchor="w"
    )
    if sub:
        ctk.CTkLabel(wrap, text=sub, font=("Segoe UI", 13), text_color=p["muted"]).pack(
            anchor="w", pady=(2, 0)
        )
    return wrap


def badge(parent, text, color=ACCENT):
    b = ctk.CTkLabel(
        parent,
        text=f"  {text}  ",
        font=("Segoe UI Semibold", 11),
        text_color="white",
        fg_color=color,
        corner_radius=999,
        padx=2,
    )
    return b


def fuzzy_match(query: str, text: str) -> bool:
    """True if every char of query appears in text in order (subsequence)."""
    q = (query or "").lower().strip()
    if not q:
        return True
    it = iter((text or "").lower())
    return all(ch in it for ch in q)


def _fuzzy_score(query: str, text: str) -> float:
    q = (query or "").lower().strip()
    t = (text or "").lower()
    if not q:
        return 0.0
    if q in t:
        return 100.0 - t.index(q)
    if fuzzy_match(q, t):
        return 50.0 - len(t) * 0.01
    return -1.0


# Only one dropdown menu open at a time (prevents stacked menus where the
# close button seems dead because an older menu is still underneath).
_ACTIVE_MENU = {"win": None, "anchor": None}


def _focus_is_inside(win):
    """True only if the application focus widget lives inside `win`.

    `win.focus_get()` returns the app-global focus widget, so a widget in
    another window must NOT count as "focused" — that bug kept menus open
    forever after clicking elsewhere.
    """
    try:
        f = win.focus_get()
    except Exception:
        return False
    if not f:
        return False
    w = f
    while w is not None:
        if w is win:
            return True
        w = getattr(w, "master", None)
    return False


def _close_active_menu():
    win = _ACTIVE_MENU.get("win")
    _ACTIVE_MENU["win"] = None
    _ACTIVE_MENU["anchor"] = None
    if win is not None:
        try:
            win.destroy()
        except Exception:
            pass


def _auto_menu_width(groups):
    longest = 8
    for _section, entries in groups:
        for label, _payload in entries:
            longest = max(longest, len(str(label)))
    return max(210, min(340, longest * 7 + 48))


def _place_dropdown(win, anchor, max_height=420):
    """Position a borderless dropdown near `anchor`, always on-screen.

    Prefers below the anchor, falls back to above, and shrinks the height
    to the available space instead of running off the edge.
    """
    try:
        win.update_idletasks()
        ax = anchor.winfo_rootx()
        ay = anchor.winfo_rooty()
        ah = anchor.winfo_height()
        w = win.winfo_reqwidth() or 220
        h = min(win.winfo_reqheight() or max_height, max_height)
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        gap = 5
        below = sh - (ay + ah) - gap - 4
        above = ay - gap - 4
        if h <= below:
            y = ay + ah + gap
        elif below >= 200:
            # prefer opening downward (shrink + scroll) over covering content
            h = below
            y = ay + ah + gap
        elif h <= above:
            y = ay - h - gap
        elif above >= below:
            h = max(170, above)
            y = ay - h - gap
        else:
            h = max(170, below)
            y = ay + ah + gap
        x = min(max(4, ax), max(4, sw - w - 4))
        y = min(max(4, y), max(4, sh - h - 4))
        win.geometry(f"{int(w)}x{int(h)}+{int(x)}+{int(y)}")
    except Exception:
        pass


def make_draggable(window, handle):
    """Allow `window` to be moved by dragging inside `handle` (a header).

    Bindings live on the window itself: events propagate up from children,
    so drags work from labels/badges in the header regardless of CTk's
    internal canvas binding redirection. Presses on interactive widgets
    (buttons, entries, text boxes) or outside the header are ignored so
    their clicks/selections still work.
    """
    st = {"active": False, "x": 0, "y": 0}

    def interactive(widget):
        while widget is not None and widget is not window:
            if isinstance(
                widget,
                (ctk.CTkButton, ctk.CTkEntry, ctk.CTkTextbox,
                 tk.Button, tk.Entry, tk.Text),
            ):
                return True
            widget = getattr(widget, "master", None)
        return False

    def in_handle(ev):
        hx, hy = handle.winfo_rootx(), handle.winfo_rooty()
        return (hx <= ev.x_root <= hx + handle.winfo_width()
                and hy <= ev.y_root <= hy + handle.winfo_height())

    def press(ev):
        st["active"] = in_handle(ev) and not interactive(ev.widget)
        st["x"], st["y"] = ev.x_root, ev.y_root

    def motion(ev):
        if not st["active"]:
            return
        dx = ev.x_root - st["x"]
        dy = ev.y_root - st["y"]
        st["x"], st["y"] = ev.x_root, ev.y_root
        x = window.winfo_x() + dx
        y = window.winfo_y() + dy
        # keep a grip of the window on-screen
        x = max(40 - window.winfo_width(), min(x, window.winfo_screenwidth() - 40))
        y = max(0, min(y, window.winfo_screenheight() - 40))
        window.geometry(f"+{int(x)}+{int(y)}")

    def release(_ev):
        st["active"] = False

    for seq, fn in (("<Button-1>", press), ("<B1-Motion>", motion),
                    ("<ButtonRelease-1>", release)):
        window.bind(seq, fn, add=True)
    try:
        handle.configure(cursor="fleur")
    except Exception:
        pass


def open_menu(anchor, groups, on_pick, width=None, max_height=340):
    """Open a small dropdown under `anchor`.

    groups: [(section_label, [(label, payload), ...]), ...]
    on_pick(payload) is called after the menu closes.
    Clicking the same anchor again toggles the menu closed.
    """
    if _ACTIVE_MENU.get("anchor") is anchor and _ACTIVE_MENU.get("win") is not None:
        _close_active_menu()
        return None
    _close_active_menu()
    if width is None:
        width = _auto_menu_width(groups)
    p = palette()
    win = ctk.CTkToplevel(anchor)
    win.overrideredirect(True)
    win.attributes("-topmost", True)
    win.configure(fg_color=p["card"])
    state = {"win": win}
    _ACTIVE_MENU["win"] = win
    _ACTIVE_MENU["anchor"] = anchor

    def close():
        if state.get("win") is None:
            return
        state["win"] = None
        if _ACTIVE_MENU.get("win") is win:
            _ACTIVE_MENU["win"] = None
            _ACTIVE_MENU["anchor"] = None
        try:
            win.destroy()
        except Exception:
            pass

    header = ctk.CTkFrame(win, fg_color="transparent")
    header.pack(fill="x", padx=8, pady=(6, 2))
    ctk.CTkLabel(
        header, text="More actions", font=("Segoe UI Semibold", 12),
        text_color=p["text"],
    ).pack(side="left", padx=4)
    ctk.CTkButton(
        header, text="✕", width=26, height=24, corner_radius=6,
        fg_color="transparent", hover_color=p["card2"],
        text_color=p["muted"], command=close,
    ).pack(side="right")

    scroll = ctk.CTkScrollableFrame(
        win, width=width, height=max_height, fg_color="transparent",
        scrollbar_button_color=p["border"],
    )
    scroll.pack(fill="both", expand=True, padx=6, pady=(0, 6))

    def pick(payload):
        close()
        on_pick(payload)

    for section, entries in groups:
        if section:
            ctk.CTkLabel(
                scroll, text=section.upper(), anchor="w",
                font=("Segoe UI", 10), text_color=p["muted"],
            ).pack(fill="x", padx=6, pady=(6, 2))
        for label, payload in entries:
            ctk.CTkButton(
                scroll, text=label, anchor="w", height=28, corner_radius=6,
                fg_color="transparent", hover_color=p["sidebar_hover"],
                text_color=p["text"], font=("Segoe UI", 12),
                command=lambda pl=payload: pick(pl),
            ).pack(fill="x", padx=2, pady=1)

    _place_dropdown(win, anchor, max_height=max_height)
    win.bind("<Escape>", lambda e: close())

    def check_focus():
        if state.get("win") is None:
            return
        try:
            if not _focus_is_inside(win):
                close()
        except Exception:
            close()

    def grab():
        if state.get("win") is None:
            return
        try:
            win.focus_force()
            win.bind("<FocusOut>", lambda e: win.after(120, check_focus))
        except Exception:
            pass

    win.after(80, grab)
    return win


class ResultActions:
    """Shared action-bar, diff rendering, and keyboard support for result windows.

    Subclasses must set before use:
      self.original, self.corrected, self._on_action, self._action,
      self.corr_box, self._preview_limit (int or None), self._status (label)
    """

    NAV_KEYS = {"left", "right", "up", "down"}
    LETTER_KEYS = {"r", "c", "i", "p"}

    # --- rendering -----------------------------------------------------
    def _inner_text(self):
        """Underlying tkinter Text widget (CTkTextbox does not expose tags)."""
        box = self.corr_box
        return getattr(box, "_textbox", box)

    def _set_result_text(self, text):
        self.corrected = text
        box = self.corr_box
        limit = self._preview_limit
        try:
            spans = diff_spans(self.original, text)
            truncated = bool(limit and len(text) > limit)
            if truncated:
                spans = preview_spans(spans, limit)
            inner = self._inner_text()
            box.configure(state="normal")
            box.delete("1.0", "end")
            inner.tag_configure(
                "chg", underline=True, underlinefg=ACCENT, foreground=ACCENT
            )
            for segment, changed in spans:
                if changed:
                    inner.insert("end", segment, "chg")
                else:
                    inner.insert("end", segment)
            if truncated:
                inner.insert("end", "…")
            box.configure(state="disabled")
        except Exception:
            try:
                box.configure(state="normal")
                box.delete("1.0", "end")
                box.insert("1.0", text)
                box.configure(state="disabled")
            except Exception:
                pass

    # --- action row ----------------------------------------------------
    def _build_action_row(self, parent):
        if not getattr(self, "_on_action", None):
            return
        p = palette()
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=12 if self._compact else 18, pady=(0, 4))
        entries = [
            ("Proofread", {"action": "proofread"}),
            ("Improve", {"action": "improve"}),
            ("Explain", {"action": "explain"}),
        ]
        for label, spec in entries:
            btn = ctk.CTkButton(
                row, text=label, width=74 if not self._compact else 66,
                height=28, corner_radius=7, fg_color=p["card2"],
                border_width=1, border_color=p["border"], text_color=p["text"],
                hover_color=p["sidebar_hover"], font=("Segoe UI", 11),
                command=lambda s=spec: self._run_action(s),
            )
            btn.pack(side="left", padx=(0, 5))
            self._register_nav(btn)
        self.more_btn = ctk.CTkButton(
            row, text="More ▾", width=68, height=28, corner_radius=7,
            fg_color="transparent", border_width=1, border_color=p["border"],
            text_color=p["muted"], hover_color=p["sidebar_hover"],
            font=("Segoe UI", 11), command=self._open_more,
        )
        self.more_btn.pack(side="left", padx=(0, 5))
        self._register_nav(self.more_btn)
        self._action_status = ctk.CTkLabel(
            row, text="", font=("Segoe UI", 10), text_color=p["muted"]
        )
        self._action_status.pack(side="right")

    def _open_more(self):
        groups = [
            (
                "Actions",
                [
                    ("Fix grammar only", {"action": "grammar"}),
                    ("Clean up fillers", {"action": "clean"}),
                    ("Format", {"action": "format"}),
                    ("Summarize", {"action": "summarize"}),
                    ("Make a prompt", {"action": "promptify"}),
                ],
            ),
        ]
        commands = get("my_commands") or []
        if commands:
            groups.append(
                (
                    "My Commands",
                    [
                        (c.get("name", ""), {"command": c.get("prompt", ""),
                                             "name": c.get("name", "")})
                        for c in commands
                        if c.get("name")
                    ],
                )
            )
        open_menu(self.more_btn, groups, self._run_action)

    def _run_action(self, spec):
        if not getattr(self, "_on_action", None):
            return
        self._set_actions_enabled(False)
        if getattr(self, "_action_status", None) is not None:
            self._action_status.configure(text="Working…", text_color=ACCENT)

        def done(text, err, provider=""):
            if not self.winfo_exists():
                return
            self._set_actions_enabled(True)
            if getattr(self, "_action_status", None) is not None:
                if err or not text:
                    self._action_status.configure(
                        text=f"Failed: {err or 'no result'}"[:70], text_color=DANGER
                    )
                else:
                    self._action_status.configure(text="✓ updated", text_color=SUCCESS)
                    self.after(2500, lambda: self._clear_status())
            if not err and text:
                self._set_result_text(str(text))

        self._on_action(spec, done)

    def _clear_status(self):
        try:
            if self.winfo_exists() and getattr(self, "_action_status", None) is not None:
                self._action_status.configure(text="")
        except Exception:
            pass

    def _set_actions_enabled(self, enabled):
        state = "normal" if enabled else "disabled"
        for btn in getattr(self, "_nav", []):
            try:
                btn.configure(state=state)
            except Exception:
                pass

    # --- keyboard navigation -------------------------------------------
    def _register_nav(self, btn):
        if not hasattr(self, "_nav"):
            self._nav = []
            self._nav_idx = None
            self._nav_styles = {}
        try:
            self._nav_styles[btn] = (
                btn.cget("border_width"), btn.cget("border_color")
            )
        except Exception:
            self._nav_styles[btn] = (1, palette()["border"])
        self._nav.append(btn)

    def _nav_move(self, delta):
        if not getattr(self, "_nav", None):
            return
        self._nav_clear_style()
        cur = self._nav_idx if self._nav_idx is not None else -1
        idx = (cur + delta) % len(self._nav)
        self._nav_idx = idx
        btn = self._nav[idx]
        try:
            btn.configure(border_width=2, border_color=ACCENT)
            btn.focus_set()
        except Exception:
            pass

    def _nav_clear_style(self):
        for btn in getattr(self, "_nav", []):
            bw, bc = getattr(self, "_nav_styles", {}).get(btn, (1, palette()["border"]))
            try:
                btn.configure(border_width=bw, border_color=bc)
            except Exception:
                pass

    def _on_key(self, event):
        k = (event.keysym or "").lower()
        if k in self.NAV_KEYS:
            delta = 1 if k in ("right", "down") else -1
            self._nav_move(delta)
            return "break"
        if k in ("return", "kp_enter"):
            if self._nav_idx is not None and getattr(self, "_nav", None):
                self._nav[self._nav_idx].invoke()
            else:
                self._result_replace()
            return "break"
        if k == "escape":
            self._result_close()
            return "break"
        if k == "r":
            self._result_replace()
            return "break"
        if k == "c":
            self._result_copy()
            return "break"
        if k == "i":
            self._result_close()
            return "break"
        if k == "p" and getattr(self, "_on_action", None):
            self._run_action({"action": "proofread"})
            return "break"
        return None


class Popup(ResultActions, ctk.CTkToplevel):
    def __init__(self, master, original, corrected, on_replace, on_copy,
                 provider="", on_translate=None, on_action=None,
                 action="proofread", action_name=None):
        super().__init__(master)
        p = palette()
        self.title("TextMate AI")
        self.geometry("680x590")
        self.minsize(500, 420)
        self.configure(fg_color=p["bg"])
        self.attributes("-topmost", True)
        self.after(150, self.focus_force)
        self._on_replace = on_replace
        self._on_copy = on_copy
        self._on_action = on_action
        self._action = action
        self.original = original
        self.corrected = corrected
        self._preview_limit = None
        self._compact = False
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=18, pady=(16, 6))
        left = ctk.CTkFrame(header, fg_color="transparent")
        left.pack(side="left")
        title = action_name or action_label(action)
        ctk.CTkLabel(left, text=f"✦ {title}", font=("Segoe UI Semibold", 18), text_color=p["text"]).pack(
            anchor="w"
        )
        if provider:
            badge(header, PROVIDER_LABELS.get(provider, provider), ACCENT).pack(side="right")
        make_draggable(self, header)

        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=14, pady=6)

        def labeled(box_parent, label):
            ctk.CTkLabel(
                box_parent, text=label, font=("Segoe UI Semibold", 12), text_color=p["muted"]
            ).pack(anchor="w", pady=(8, 6))

        orig_card = Card(body)
        orig_card.pack(fill="x", pady=(0, 10))
        labeled(orig_card, "ORIGINAL")
        original_box = ctk.CTkTextbox(
            orig_card, height=130, wrap="word", fg_color=p["card2"],
            border_width=0, text_color=p["text"]
        )
        original_box.pack(fill="x", padx=12, pady=(0, 12))
        original_box.insert("1.0", original)
        original_box.configure(state="disabled")

        corr_card = Card(body)
        corr_card.pack(fill="x", pady=(0, 6))
        labeled(corr_card, "RESULT")
        corrected_box = ctk.CTkTextbox(
            corr_card, height=130, wrap="word", fg_color=p["card2"],
            border_width=0, text_color=p["text"]
        )
        corrected_box.pack(fill="x", padx=12, pady=(0, 12))
        self.corr_box = corrected_box
        self._set_result_text(corrected)

        self._build_action_row(body)

        if on_translate:
            self.translate_ctl = TranslateControl(self, self, on_translate)

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=18, pady=(4, 18))

        replace_btn = ctk.CTkButton(
            btns, text="Replace", command=self._replace, width=150, height=40,
            fg_color=ACCENT, hover_color="#3a76e0", corner_radius=10,
            font=("Segoe UI Semibold", 13),
        )
        replace_btn.pack(side="left", padx=(0, 10))
        copy_btn = ctk.CTkButton(
            btns, text="Copy", command=self._copy, width=110, height=40,
            fg_color=p["card2"], hover_color=p["border"], border_width=1,
            border_color=p["border"], text_color=p["text"], corner_radius=10,
        )
        copy_btn.pack(side="left", padx=10)
        cancel_btn = ctk.CTkButton(
            btns, text="Cancel", command=self.destroy, width=110, height=40,
            fg_color="transparent", hover_color=p["border"], border_width=1,
            border_color=p["border"], text_color=p["muted"], corner_radius=10,
        )
        cancel_btn.pack(side="left", padx=10)
        self._register_nav(replace_btn)
        self._register_nav(copy_btn)
        self._register_nav(cancel_btn)

        ctk.CTkLabel(
            btns, text="R=Replace · C=Copy · I=Close · arrows+Enter",
            font=("Segoe UI", 11), text_color=p["muted"]
        ).pack(side="right")

        self.bind("<Key>", self._on_key)

    def _result_replace(self):
        self._replace()

    def _result_copy(self):
        self._copy()

    def _result_close(self):
        self.destroy()

    def _replace(self):
        cb = self._on_replace
        text = self.corrected
        self.destroy()
        cb(text)

    def _copy(self):
        cb = self._on_copy
        text = self.corrected
        self.destroy()
        cb(text)

    def _apply_translation(self, new_text):
        self._set_result_text(new_text)


class TranslateControl:
    """'Translate ▾' button opening a scrollable language picker.

    Calls owner._apply_translation(new) via on_translate(lang, done).
    """

    PLACEHOLDER = "Translate ▾"

    def __init__(self, parent, owner, on_translate, width=150):
        self.owner = owner
        self.on_translate = on_translate
        self._menu_win = None
        p = palette()
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(0, 6))
        ctk.CTkLabel(
            row, text="Translate:", font=("Segoe UI", 12), text_color=p["muted"]
        ).pack(side="left")
        self.btn = ctk.CTkButton(
            row, text=self.PLACEHOLDER, width=width, height=30, corner_radius=8,
            fg_color=p["card2"], border_width=1, border_color=p["border"],
            text_color=p["text"], hover_color=p["sidebar_hover"],
            font=("Segoe UI", 12), command=self._toggle_menu,
        )
        self.btn.pack(side="left", padx=(8, 8))
        self.status = ctk.CTkLabel(
            row, text="", font=("Segoe UI", 11), text_color=p["muted"]
        )
        self.status.pack(side="left")

    # --- picker menu ---
    def _toggle_menu(self):
        if self._menu_win is not None:
            self._close_menu()
            return
        p = palette()
        win = ctk.CTkToplevel(self.btn)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(fg_color=p["card"])
        self._menu_win = win

        header = ctk.CTkFrame(win, fg_color="transparent")
        header.pack(fill="x", padx=8, pady=(6, 2))
        ctk.CTkLabel(
            header, text="Translate to", font=("Segoe UI Semibold", 12),
            text_color=p["text"],
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            header, text="✕", width=26, height=24, corner_radius=6,
            fg_color="transparent", hover_color=p["card2"],
            text_color=p["muted"], command=self._close_menu,
        ).pack(side="right")

        height = 340
        scroll = ctk.CTkScrollableFrame(
            win, width=196, height=height, fg_color="transparent",
            label_text="", scrollbar_button_color=p["border"],
        )
        scroll.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        for group_name, langs in TRANSLATE_LANG_GROUPS:
            ctk.CTkLabel(
                scroll, text=group_name.upper(), anchor="w",
                font=("Segoe UI", 10), text_color=p["muted"],
            ).pack(fill="x", padx=6, pady=(6, 2))
            for lang in langs:
                ctk.CTkButton(
                    scroll, text=lang, anchor="w", height=28, corner_radius=6,
                    fg_color="transparent", hover_color=p["sidebar_hover"],
                    text_color=p["text"], font=("Segoe UI", 12),
                    command=lambda l=lang: self._pick(l),
                ).pack(fill="x", padx=2, pady=1)

        self._position_menu()
        win.bind("<Escape>", lambda e: self._close_menu())
        win.after(60, self._grab_and_close_on_focus_out)

    def _position_menu(self):
        _place_dropdown(self._menu_win, self.btn, max_height=380)

    def _grab_and_close_on_focus_out(self):
        win = self._menu_win
        if win is None:
            return
        try:
            win.focus_force()
            win.bind(
                "<FocusOut>",
                lambda e: self._root_after_close_check(),
            )
        except Exception:
            pass

    def _root_after_close_check(self):
        # Close only if focus really left the menu (not a transient glitch)
        win = self._menu_win
        if win is None:
            return
        try:
            if not _focus_is_inside(win):
                self._close_menu()
        except Exception:
            self._close_menu()

    def _close_menu(self):
        win = self._menu_win
        self._menu_win = None
        if win is not None:
            try:
                win.destroy()
            except Exception:
                pass

    def _pick(self, lang):
        self._close_menu()
        self._select(lang)

    # --- translation run ---
    def _select(self, choice):
        if not choice or choice == self.PLACEHOLDER:
            return
        lang = choice
        self.btn.configure(state="disabled")
        self.status.configure(text=f"Translating to {lang}…", text_color=ACCENT)
        text = getattr(self.owner, "corrected", "")
        self.on_translate(lang, self._done, text)

    def _done(self, new_text, err=None):
        try:
            self.btn.configure(state="normal")
        except Exception:
            pass
        if err or not new_text:
            self.status.configure(
                text=f"Failed: {err or 'no result'}"[:80], text_color=DANGER
            )
            return
        self.status.configure(text="✓ translated", text_color=SUCCESS)
        try:
            self.owner._apply_translation(new_text)
        except Exception:
            pass


class ResultOverlay(ResultActions, ctk.CTkToplevel):
    """Compact floating toolbar shown near the cursor after a proofread.

    Buttons: Replace / Copy / Ignore plus an action bar (Proofread, Improve,
    Explain, More). Stays open until the user acts.
    """

    def __init__(self, master, original, corrected, on_replace, on_copy,
                 provider="", on_translate=None, on_action=None,
                 action="proofread", action_name=None):
        super().__init__(master)
        p = palette()
        self.overrideredirect(True)
        self.configure(fg_color=p["card"])
        self.attributes("-topmost", True)
        self._on_replace = on_replace
        self._on_copy = on_copy
        self._on_action = on_action
        self._action = action
        self.original = original
        self.corrected = corrected
        self._preview_limit = 240
        self._compact = True

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(10, 2))
        title = action_name or action_label(action)
        ctk.CTkLabel(
            header, text=f"✦ {title}", font=("Segoe UI Semibold", 12),
            text_color=ACCENT,
        ).pack(side="left")
        if provider:
            badge(header, PROVIDER_LABELS.get(provider, provider), ACCENT).pack(
                side="right"
            )
        make_draggable(self, header)

        box = ctk.CTkTextbox(
            self, height=64, width=340, wrap="word", fg_color=p["card2"],
            border_width=1, border_color=p["border"], text_color=p["text"],
            font=("Segoe UI", 12),
        )
        box.pack(fill="x", padx=12, pady=(4, 8))
        self.corr_box = box
        self._set_result_text(corrected)

        self._build_action_row(self)

        if on_translate:
            self.translate_ctl = TranslateControl(self, self, on_translate, width=132)

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=12, pady=(0, 10))
        replace_btn = ctk.CTkButton(
            btns, text="Replace", command=self._replace, width=110, height=34,
            fg_color=ACCENT, hover_color="#3a76e0", corner_radius=8,
            font=("Segoe UI Semibold", 12),
        )
        replace_btn.pack(side="left", padx=(0, 6))
        copy_btn = ctk.CTkButton(
            btns, text="Copy", command=self._copy, width=80, height=34,
            fg_color=p["card2"], hover_color=p["border"], border_width=1,
            border_color=p["border"], text_color=p["text"], corner_radius=8,
        )
        copy_btn.pack(side="left", padx=6)
        close_btn = ctk.CTkButton(
            btns, text="Ignore", command=self.destroy, width=80, height=34,
            fg_color="transparent", hover_color=p["border"], border_width=1,
            border_color=p["border"], text_color=p["muted"], corner_radius=8,
        )
        close_btn.pack(side="left", padx=6)
        self._register_nav(replace_btn)
        self._register_nav(copy_btn)
        self._register_nav(close_btn)
        ctk.CTkLabel(
            btns, text="R/C/I · arrows+Enter · Esc",
            font=("Segoe UI", 10), text_color=p["muted"],
        ).pack(side="right")

        self.bind("<Key>", self._on_key)

        self._place_near_cursor()
        self.after_idle(self.focus_force)

    def _result_replace(self):
        self._replace()

    def _result_copy(self):
        self._copy()

    def _result_close(self):
        self.destroy()

    def _place_near_cursor(self):
        try:
            from ctypes import wintypes
            import ctypes

            pt = wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            x, y = pt.x + 16, pt.y + 16
        except Exception:
            pt = None
            x, y = 200, 200
        try:
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            self.update_idletasks()
            w = self.winfo_reqwidth() or 380
            h = self.winfo_reqheight() or 160
            if x + w > sw:
                x = max(4, (pt.x if pt else 200) - w - 16)
            if y + h > sh:
                y = max(4, (pt.y if pt else 200) - h - 16)
            self.geometry(f"+{x}+{y}")
        except Exception:
            self.geometry(f"+{x}+{y}")

    def _replace(self):
        cb = self._on_replace
        text = self.corrected
        self.destroy()
        cb(text)

    def _copy(self):
        cb = self._on_copy
        text = self.corrected
        self.destroy()
        cb(text)

    def _apply_translation(self, new_text):
        self._set_result_text(new_text)


def palette_items() -> list:
    items = []
    for aid, spec in ACTIONS.items():
        items.append({"id": f"action:{aid}", "label": spec["label"], "group": "Actions"})
    for label, hint in SUMMARIZE_PRESETS:
        items.append({"id": f"summary:{hint}", "label": label, "group": "Summarize"})
    for i, cmd in enumerate(get("my_commands") or []):
        name = str(cmd.get("name") or "").strip()
        if name:
            items.append({"id": f"command:{i}", "label": name, "group": "My Commands"})
    items.append({"id": "undo", "label": "Undo last replace", "group": "Utilities"})
    items.append({"id": "settings", "label": "Open Settings", "group": "Utilities"})
    return items


class CommandPalette(ctk.CTkToplevel):
    """Fuzzy-search launcher: pick an action, then it runs on the selection."""

    MAX_ROWS = 10

    def __init__(self, master, on_pick):
        super().__init__(master)
        p = palette()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(fg_color=p["card"])
        self._on_pick = on_pick
        self._items = palette_items()
        self._filtered = list(self._items)
        self._sel = 0
        self._rows = []

        width = 540
        self.entry = ctk.CTkEntry(
            self, height=46, width=width, corner_radius=10,
            fg_color=p["card2"], border_color=ACCENT, text_color=p["text"],
            placeholder_text="What do you want to do?  type to filter · ↑↓ · Enter",
            font=("Segoe UI", 14),
        )
        self.entry.pack(fill="x", padx=12, pady=(12, 6))

        self.scroll = ctk.CTkScrollableFrame(
            self, width=width, height=330, fg_color="transparent",
            scrollbar_button_color=p["border"],
        )
        self.scroll.pack(fill="both", padx=12, pady=(0, 6))

        self._render_rows()
        self.bind("<Key>", self._on_key)
        self.entry.bind("<KeyRelease>", lambda e: self._refilter())

        self._center(width)
        self.after_idle(lambda: (self.focus_force(), self.entry.focus_set()))

    def _center(self, width):
        try:
            self.update_idletasks()
            sw = self.winfo_screenwidth()
            h = self.winfo_reqheight() or 400
            x = max(8, (sw - width) // 2)
            y = max(40, int(self.winfo_screenheight() * 0.18))
            self.geometry(f"{width}x{h}+{x}+{y}")
        except Exception:
            self.geometry(f"540x400+200+150")

    def _refilter(self):
        query = self.entry.get()
        scored = []
        for item in self._items:
            s = _fuzzy_score(query, item["label"])
            if s >= 0:
                scored.append((s, item))
        scored.sort(key=lambda pair: -pair[0])
        self._filtered = [item for _s, item in scored]
        self._sel = 0
        self._render_rows()

    def _render_rows(self):
        for row in self._rows:
            try:
                row.destroy()
            except Exception:
                pass
        self._rows = []
        p = palette()
        if not self._filtered:
            lbl = ctk.CTkLabel(
                self.scroll, text="No match", font=("Segoe UI", 12),
                text_color=p["muted"],
            )
            lbl.pack(pady=14)
            self._rows.append(lbl)
            return
        self._sel = max(0, min(self._sel, len(self._filtered) - 1))
        for idx, item in enumerate(self._filtered[: self.MAX_ROWS]):
            is_sel = idx == self._sel
            btn = ctk.CTkButton(
                self.scroll, text=f"{item['label']}   ·  {item['group']}",
                anchor="w", height=32, corner_radius=8,
                fg_color=ACCENT_SOFT if is_sel else "transparent",
                border_width=1,
                border_color=ACCENT if is_sel else p["border"],
                text_color=p["text"], font=("Segoe UI", 12),
                hover_color=p["sidebar_hover"],
                command=lambda i=idx: self._pick_idx(i),
            )
            btn.pack(fill="x", pady=1)
            self._rows.append(btn)

    def _move(self, delta):
        if not self._filtered:
            return
        visible = min(len(self._filtered), self.MAX_ROWS)
        self._sel = (self._sel + delta) % visible
        self._render_rows()

    def _pick_idx(self, idx):
        if idx < 0 or idx >= len(self._filtered):
            return
        pick_id = self._filtered[idx]["id"]
        try:
            self.destroy()
        except Exception:
            pass
        self._on_pick(pick_id)

    def _on_key(self, event):
        k = (event.keysym or "").lower()
        if k in ("down",):
            self._move(1)
            return "break"
        if k in ("up",):
            self._move(-1)
            return "break"
        if k in ("return", "kp_enter"):
            self._pick_idx(self._sel)
            return "break"
        if k == "escape":
            self.destroy()
            return "break"
        return None


_open_palette_ref = {"win": None}


def open_command_palette(master, on_pick):
    existing = _open_palette_ref.get("win")
    if existing is not None:
        try:
            if existing.winfo_exists():
                existing.focus_force()
                return existing
        except Exception:
            pass
    win = CommandPalette(master, on_pick)
    _open_palette_ref["win"] = win
    return win


class RegionSelector(ctk.CTkToplevel):
    """Fullscreen drag-to-select overlay for screenshot OCR.

    Calls on_done((x0, y0, x1, y1)) or on_done(None) on cancel.
    """

    MIN_SIZE = 8

    def __init__(self, master, on_done):
        super().__init__(master)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self._on_done = on_done
        self._start = None
        self._rect = None
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{sw}x{sh}+0+0")
        try:
            self.attributes("-alpha", 0.35)
        except Exception:
            pass
        self.configure(fg_color="#0b0f14")

        self.canvas = tk.Canvas(
            self, bg="#0b0f14", highlightthickness=0, cursor="crosshair"
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_text(
            sw // 2, 46,
            text="Drag to select text  ·  Esc or right-click to cancel",
            fill="#e8edf7", font=("Segoe UI", 14, "bold"),
        )

        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.bind("<Escape>", lambda e: self._cancel())
        self.canvas.bind("<ButtonPress-3>", lambda e: self._cancel())
        self.after_idle(self.focus_force)

    def _press(self, event):
        self._start = (event.x, event.y)
        self._rect = self.canvas.create_rectangle(
            event.x, event.y, event.x, event.y,
            outline=ACCENT, width=2,
        )

    def _drag(self, event):
        if self._start is None or self._rect is None:
            return
        self.canvas.coords(
            self._rect, self._start[0], self._start[1], event.x, event.y
        )

    def _release(self, event):
        if self._start is None:
            return
        x0, y0 = self._start
        x1, y1 = event.x, event.y
        self._start = None
        bbox = (
            min(x0, x1),
            min(y0, y1),
            max(x0, x1),
            max(y0, y1),
        )
        valid = (bbox[2] - bbox[0]) >= self.MIN_SIZE and (bbox[3] - bbox[1]) >= self.MIN_SIZE
        done = self._on_done
        try:
            self.destroy()
        except Exception:
            pass
        done(bbox if valid else None)

    def _cancel(self):
        done = self._on_done
        self._start = None
        try:
            self.destroy()
        except Exception:
            pass
        done(None)


def open_region_selector(master, on_done):
    return RegionSelector(master, on_done)


class LoadingPopup(ctk.CTkToplevel):
    def __init__(self, master, text="Checking text"):
        super().__init__(master)
        p = palette()
        self.title("TextMate AI")
        self.geometry("340x150")
        self.resizable(False, False)
        self.configure(fg_color=p["bg"])
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", lambda: None)
        self._dots = 0
        # Never steal focus from the source app during capture
        self.after_idle(self._noactivate)

        card = Card(self)
        card.pack(fill="both", expand=True, padx=14, pady=14)
        ctk.CTkLabel(card, text="TextMate AI", font=("Segoe UI", 11), text_color=p["muted"]).pack(
            pady=(18, 4)
        )
        self._label = ctk.CTkLabel(
            card, text=text, font=("Segoe UI Semibold", 15), text_color=p["text"]
        )
        self._label.pack()
        self._bar = ctk.CTkProgressBar(card, width=200, height=6, corner_radius=99)
        self._bar.pack(pady=(16, 18))
        self._bar.configure(mode="indeterminate", progress_color=ACCENT)
        try:
            self._bar.start()
        except TypeError:
            pass
        self._tick()

    def _noactivate(self):
        try:
            import ctypes

            hwnd = int(self.wm_frame(), 16)
            if not hwnd:
                return
            GWL_EXSTYLE = -20
            WS_EX_NOACTIVATE = 0x08000000
            WS_EX_TOOLWINDOW = 0x00000080
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd,
                GWL_EXSTYLE,
                style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW,
            )
        except Exception:
            pass

    def _tick(self):
        if not self.winfo_exists():
            return
        self._dots = (self._dots + 1) % 4
        self._label.configure(text="Checking text" + "." * self._dots)
        self.after(400, self._tick)

    def close(self):
        if self.winfo_exists():
            try:
                self._bar.stop()
            except Exception:
                pass
            try:
                self.destroy()
            except Exception:
                pass


def show_message(master, title, message, error=False):
    p = palette()
    win = ctk.CTkToplevel(master)
    win.title("TextMate AI")
    win.geometry("460x210")
    win.configure(fg_color=p["bg"])
    win.attributes("-topmost", True)
    win.after(150, win.focus_force)
    card = Card(win)
    card.pack(fill="both", expand=True, padx=14, pady=14)
    ctk.CTkLabel(
        card,
        text=title,
        font=("Segoe UI Semibold", 16),
        text_color=DANGER if error else p["text"],
    ).pack(pady=(22, 8))
    ctk.CTkLabel(
        card, text=message, wraplength=400, justify="center",
        font=("Segoe UI", 13), text_color=p["muted"]
    ).pack(padx=14, expand=True)
    ctk.CTkButton(
        card, text="OK", command=win.destroy, width=100, height=36,
        fg_color=ACCENT, corner_radius=10,
    ).pack(pady=(8, 18))
    win.bind("<Return>", lambda e: win.destroy())
    win.bind("<Escape>", lambda e: win.destroy())
    return win


def show_error(master, message):
    return show_message(master, "Correction failed", message, error=True)


class StatCard(ctk.CTkFrame):
    def __init__(self, master, label, value="0"):
        p = palette()
        super().__init__(master, corner_radius=14, fg_color=p["card"],
                         border_width=1, border_color=p["border"], height=96)
        self.pack_propagate(False)
        self.value_lbl = ctk.CTkLabel(
            self, text=value, font=("Segoe UI Semibold", 26), text_color=ACCENT
        )
        self.value_lbl.pack(pady=(16, 0))
        ctk.CTkLabel(self, text=label, font=("Segoe UI", 12), text_color=p["muted"]).pack()

    def set(self, value):
        self.value_lbl.configure(text=str(value))


class HomePage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._build()

    def _build(self):
        p = palette()
        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=10, pady=10)

        section_title(outer, "Dashboard", "Universal grammar assistant for every app")

        status = Card(outer)
        status.pack(fill="x", pady=(0, 14))

        hero = ctk.CTkFrame(status, fg_color="transparent")
        hero.pack(fill="x", padx=18, pady=(18, 6))

        icon = ctk.CTkLabel(
            hero, text="✦", font=("Segoe UI", 28), text_color=ACCENT, width=44
        )
        icon.pack(side="left", padx=(0, 12))

        info = ctk.CTkFrame(hero, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True)
        title_row = ctk.CTkFrame(info, fg_color="transparent")
        title_row.pack(anchor="w")
        self.status_title = ctk.CTkLabel(
            title_row, text="Running", font=("Segoe UI Semibold", 18), text_color=p["text"]
        )
        self.status_title.pack(side="left")
        self.status_pill = badge(title_row, "ACTIVE", SUCCESS)
        self.status_pill.pack(side="left", padx=(10, 0))

        self.status_sub = ctk.CTkLabel(
            info,
            text="Ready — select text and press the hotkey",
            font=("Segoe UI", 13),
            text_color=p["muted"],
        )
        self.status_sub.pack(anchor="w", pady=(4, 0))

        self.enable_switch = ctk.CTkSwitch(
            hero,
            text="Enabled",
            command=self._toggle,
            width=110,
            progress_color=ACCENT,
            button_color="white",
            button_hover_color="#e8edf7",
            font=("Segoe UI Semibold", 13),
        )
        self.enable_switch.pack(side="right")
        if get("enabled", True):
            self.enable_switch.select()
        else:
            self.enable_switch.deselect()

        hk = ctk.CTkFrame(status, fg_color=p["card2"], corner_radius=10, border_width=1,
                          border_color=p["border"])
        hk.pack(fill="x", padx=18, pady=(8, 6))
        row = ctk.CTkFrame(hk, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=10)
        ctk.CTkLabel(row, text="Hotkey", font=("Segoe UI", 12), text_color=p["muted"]).pack(
            side="left"
        )
        hotkey = (get("hotkey") or "ctrl+alt+z").upper().replace("+", "  +  ")
        ctk.CTkLabel(
            row, text=hotkey, font=("Consolas", 14, "bold"), text_color=p["text"]
        ).pack(side="right")

        ctk.CTkFrame(status, fg_color="transparent").pack(pady=(2, 10))

        stats = ctk.CTkFrame(outer, fg_color="transparent")
        stats.pack(fill="x", pady=(0, 14))
        for i in range(3):
            stats.columnconfigure(i, weight=1, uniform="st")
        self.s1 = StatCard(stats, "Corrections")
        self.s1.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.s2 = StatCard(stats, "Last provider")
        self.s2.grid(row=0, column=1, sticky="nsew", padx=8)
        self.s3 = StatCard(stats, "API keys")
        self.s3.grid(row=0, column=2, sticky="nsew", padx=(8, 0))

        self.after(80, self.refresh)

    def _toggle(self):
        self.app.set_enabled(bool(self.enable_switch.get()))

    def refresh(self):
        enabled = bool(get("enabled", True))
        try:
            if enabled:
                self.enable_switch.select()
            else:
                self.enable_switch.deselect()
        except Exception:
            pass
        self.status_title.configure(text="Running" if enabled else "Disabled")
        self.status_pill.configure(
            text="  ACTIVE  " if enabled else "  PAUSED  ",
            fg_color=SUCCESS if enabled else DANGER,
        )
        self.status_sub.configure(
            text="Ready — select text and press the hotkey"
            if enabled
            else "Hotkey is paused — enable to proofread"
        )

        items = history_store.list_items()
        self.s1.set(len(items))
        import llm

        last = getattr(llm, "LAST_PROVIDER", "") or "—"
        self.s2.set(PROVIDER_LABELS.get(last, last) if last != "—" else "—")
        keys_on = [k for k, v in API_KEYS.items() if v]
        self.s3.set(len(keys_on))


GUIDE_STEPS = [
    {"n": "01", "title": "Select text anywhere",
     "body": "Highlight text in Word, Excel, PowerPoint, browser, Notepad — any Windows app."},
    {"n": "02", "title": "Press the hotkey",
     "body": "Hit Ctrl + Alt + Z (configurable in Settings). The app copies the selection automatically."},
    {"n": "03", "title": "AI fixes grammar & tone",
      "body": "Free LLM providers correct grammar and tone in any language — with automatic fallback."},
    {"n": "04", "title": "Review & replace",
     "body": "A clean popup shows original vs result — changed words are highlighted. "
             "Press Enter to Replace, or Copy / Cancel. Keyboard: R, C, I, arrows+Enter."},
    {"n": "05", "title": "More AI actions",
     "body": "In the result window use Proofread · Improve · Explain, or open More ▾ for "
             "Fix grammar only, Clean up fillers, Format, Summarize, Make a prompt, "
             "and your own My Commands."},
    {"n": "06", "title": "Command palette",
     "body": "Press Ctrl + Alt + Space for a search box over every action — "
             "type \"email\", \"assamese\" or \"simple\" and hit Enter, "
             "then select the text you want it applied to."},
    {"n": "07", "title": "Screenshot OCR",
     "body": "Press Ctrl + Alt + O, drag over any text on screen (image, PDF, video frame) — "
             "AI reads the picture (Windows OCR as offline fallback) and opens the normal "
             "result window."},
    {"n": "08", "title": "Setup — Get a free API key",
     "body": "Open Settings → Providers → click \"Get key\" next to Groq (or Gemini / NVIDIA / DeepSeek). "
             "Create a free account and copy your API key. Groq is recommended — fast and free. "
             "You bring your own key; nothing is bundled with the app."},
    {"n": "09", "title": "Setup — Paste key & Save",
     "body": "Back in Settings → Providers, paste the key into the provider field, click Test (optional), "
             "then Save changes. No restart needed — the hotkey works immediately."},
    {"n": "10", "title": "Runs quietly in the tray",
     "body": "Close the window to hide to tray. Reopen anytime by double-clicking the tray icon. "
             "App keeps listening for the hotkey in the background. Ctrl + Alt + U undoes "
             "the last Replace."},
]


class GuidePage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.index = 0
        p = palette()

        section_title(self, "How it works", "Usage + setup steps")

        self.body = Card(self)
        self.body.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        top = ctk.CTkFrame(self.body, fg_color="transparent")
        top.pack(fill="x", padx=28, pady=(36, 0))
        self.step_badge = ctk.CTkLabel(
            top, text="", font=("Segoe UI Semibold", 13),
            text_color="white", fg_color=ACCENT, corner_radius=999,
        )
        self.step_badge.pack(anchor="w")

        self.title = ctk.CTkLabel(
            self.body, text="", font=("Segoe UI Semibold", 26), text_color=p["text"]
        )
        self.title.pack(anchor="w", padx=28, pady=(18, 10))

        self.text = ctk.CTkLabel(
            self.body, text="", wraplength=480, justify="left",
            font=("Segoe UI", 15), text_color=p["muted"], anchor="w",
        )
        self.text.pack(anchor="w", padx=28, pady=(0, 8))

        self.progress = ctk.CTkProgressBar(self.body, height=6, corner_radius=99)
        self.progress.pack(fill="x", padx=28, pady=(24, 8))
        self.progress.configure(progress_color=ACCENT)

        self.dots_frame = ctk.CTkFrame(self.body, fg_color="transparent")
        self.dots_frame.pack(padx=28, pady=(4, 8))
        self.dots = []
        for _ in GUIDE_STEPS:
            d = ctk.CTkLabel(self.dots_frame, text="●", text_color=p["border"], width=14)
            d.pack(side="left", padx=4)
            self.dots.append(d)

        nav = ctk.CTkFrame(self, fg_color="transparent")
        nav.pack(fill="x", padx=10, pady=(0, 12))
        self.back_btn = ctk.CTkButton(
            nav, text="Back", width=110, height=40, fg_color="transparent",
            border_width=1, border_color=p["border"], text_color=p["muted"],
            hover_color=p["card2"], corner_radius=10, command=self.prev,
        )
        self.back_btn.pack(side="left")
        self.skip_btn = ctk.CTkButton(
            nav, text="Skip", width=90, height=40, fg_color="transparent",
            hover_color=p["card2"], text_color=p["muted"], corner_radius=10,
            command=self.app.complete_onboarding,
        )
        self.skip_btn.pack(side="left", padx=10)
        self.next_btn = ctk.CTkButton(
            nav, text="Next", width=140, height=40, fg_color=ACCENT,
            hover_color="#3a76e0", corner_radius=10,
            font=("Segoe UI Semibold", 13), command=self.next,
        )
        self.next_btn.pack(side="right")

        self.render()

    def render(self):
        p = palette()
        step = GUIDE_STEPS[self.index]
        self.step_badge.configure(text=f"  STEP {step['n']}  ")
        self.title.configure(text=step["title"])
        self.text.configure(text=step["body"])
        pct = (self.index + 1) / len(GUIDE_STEPS)
        try:
            self.progress.set(pct)
        except Exception:
            pass
        for i, d in enumerate(self.dots):
            d.configure(text_color=ACCENT if i <= self.index else p["border"])
        last = self.index == len(GUIDE_STEPS) - 1
        self.back_btn.configure(state="disabled" if self.index == 0 else "normal")
        self.next_btn.configure(text="Get started" if last else "Next")

    def prev(self):
        if self.index > 0:
            self.index -= 1
            self.render()

    def next(self):
        if self.index < len(GUIDE_STEPS) - 1:
            self.index += 1
            self.render()
        else:
            self.app.complete_onboarding()


class SettingsPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        p = palette()

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(10, 6))
        ctk.CTkLabel(header, text="Settings", font=("Segoe UI Semibold", 22),
                     text_color=p["text"]).pack(side="left")
        ctk.CTkButton(
            header, text="Save changes", width=130, height=38, fg_color=ACCENT,
            hover_color="#3a76e0", corner_radius=10,
            font=("Segoe UI Semibold", 13), command=self.save,
        ).pack(side="right")

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        settings = load_settings()

        gen = Card(scroll)
        gen.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(gen, text="General", font=("Segoe UI Semibold", 15),
                     text_color=p["text"]).pack(anchor="w", padx=18, pady=(16, 12))

        def field_label(parent, text):
            ctk.CTkLabel(parent, text=text, font=("Segoe UI", 12),
                         text_color=p["muted"]).pack(anchor="w", padx=18, pady=(4, 4))

        field_label(gen, "Global hotkey")
        self.hotkey_var = ctk.StringVar(value=settings["hotkey"])
        ctk.CTkEntry(
            gen, textvariable=self.hotkey_var, height=38, corner_radius=10,
            fg_color=p["card2"], border_color=p["border"], text_color=p["text"],
        ).pack(fill="x", padx=18, pady=(0, 4))
        ctk.CTkLabel(gen, text="e.g. ctrl+alt+z", font=("Segoe UI", 11),
                     text_color=p["muted"]).pack(anchor="w", padx=18, pady=(0, 12))

        self.auto_var = ctk.BooleanVar(value=bool(settings["auto_replace"]))
        ctk.CTkSwitch(
            gen, text="Auto-replace without popup", variable=self.auto_var,
            progress_color=ACCENT, font=("Segoe UI", 13), text_color=p["text"],
        ).pack(anchor="w", padx=18, pady=6)

        self.enabled_var = ctk.BooleanVar(value=bool(settings["enabled"]))
        ctk.CTkSwitch(
            gen, text="Enabled at startup", variable=self.enabled_var,
            progress_color=ACCENT, font=("Segoe UI", 13), text_color=p["text"],
        ).pack(anchor="w", padx=18, pady=6)

        self.auto_update_var = ctk.BooleanVar(value=bool(settings.get("auto_update", True)))
        ctk.CTkSwitch(
            gen, text="Auto-check for updates on launch",
            variable=self.auto_update_var, progress_color=ACCENT,
            font=("Segoe UI", 13), text_color=p["text"],
        ).pack(anchor="w", padx=18, pady=(6, 10))

        ctk.CTkLabel(gen, text="Proofreading", font=("Segoe UI Semibold", 14),
                     text_color=p["text"]).pack(anchor="w", padx=18, pady=(4, 4))

        field_label(gen, "Tone preset")
        self.tone_var = ctk.StringVar(
            value=settings.get("tone", "professional") if settings.get("tone", "professional") in TONES else "professional"
        )
        tone_labels = {k: k.capitalize() for k in TONES}
        self._tone_labels = tone_labels
        ctk.CTkOptionMenu(
            gen, variable=self.tone_var, values=list(tone_labels.values()),
            height=36, corner_radius=10, fg_color=p["card2"],
            button_color=p["border"], button_hover_color=p["sidebar_hover"],
            text_color=p["text"], font=("Segoe UI", 13),
        ).pack(fill="x", padx=18, pady=(0, 4))

        field_label(gen, "Translate to (optional)")
        self.translate_var = ctk.StringVar(value=str(settings.get("translate_to", "") or ""))
        ctk.CTkEntry(
            gen, textvariable=self.translate_var, height=36, corner_radius=10,
            fg_color=p["card2"], border_color=p["border"], text_color=p["text"],
            placeholder_text="e.g. Hindi, Spanish — leave blank to keep original language",
        ).pack(fill="x", padx=18, pady=(0, 4))

        field_label(gen, "Never change these words (comma-separated)")
        self.ignore_var = ctk.StringVar(
            value=", ".join(settings.get("ignore_words") or [])
        )
        ctk.CTkEntry(
            gen, textvariable=self.ignore_var, height=36, corner_radius=10,
            fg_color=p["card2"], border_color=p["border"], text_color=p["text"],
            placeholder_text="e.g. Pranjit, Groq, myBrand",
        ).pack(fill="x", padx=18, pady=(0, 4))

        field_label(gen, "Result display")
        self.result_ui_var = ctk.StringVar(
            value="Compact overlay" if settings.get("result_ui", "overlay") != "popup" else "Full preview window"
        )
        ctk.CTkOptionMenu(
            gen, variable=self.result_ui_var,
            values=["Compact overlay", "Full preview window"],
            height=36, corner_radius=10, fg_color=p["card2"],
            button_color=p["border"], button_hover_color=p["sidebar_hover"],
            text_color=p["text"], font=("Segoe UI", 13),
        ).pack(fill="x", padx=18, pady=(0, 18))

        cmds = Card(scroll)
        cmds.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(cmds, text="My Commands", font=("Segoe UI Semibold", 15),
                     text_color=p["text"]).pack(anchor="w", padx=18, pady=(16, 2))
        ctk.CTkLabel(
            cmds,
            text="Custom AI commands — appear under “More ▾” in the result "
                 "window and in the command palette (Ctrl+Alt+Space).",
            font=("Segoe UI", 12), text_color=p["muted"],
            justify="left", wraplength=520,
        ).pack(anchor="w", padx=18, pady=(0, 8))
        self.cmd_list = ctk.CTkFrame(cmds, fg_color="transparent")
        self.cmd_list.pack(fill="x", padx=18, pady=(0, 6))
        self.cmd_rows = []
        for cmd in settings.get("my_commands") or []:
            self._add_cmd_row(
                name=str(cmd.get("name") or ""),
                prompt=str(cmd.get("prompt") or ""),
            )
        ctk.CTkButton(
            cmds, text="+ Add command", width=130, height=34, corner_radius=8,
            fg_color="transparent", border_width=1, border_color=ACCENT,
            text_color=ACCENT, hover_color=p["card"], command=self._add_cmd_row,
        ).pack(anchor="w", padx=18, pady=(2, 16))

        prov = Card(scroll)
        prov.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(prov, text="Providers", font=("Segoe UI Semibold", 15),
                     text_color=p["text"]).pack(anchor="w", padx=18, pady=(16, 4))
        ctk.CTkLabel(prov, text="Fallback order — first with a key wins",
                     font=("Segoe UI", 12), text_color=p["muted"]).pack(
            anchor="w", padx=18, pady=(0, 6)
        )

        self.smart_order_var = ctk.BooleanVar(value=bool(settings.get("smart_order", True)))
        ctk.CTkSwitch(
            prov, text="Smart order — try fastest provider first, skip recent failures",
            variable=self.smart_order_var, progress_color=ACCENT,
            font=("Segoe UI", 13), text_color=p["text"],
        ).pack(anchor="w", padx=18, pady=(0, 10))

        list_row = ctk.CTkFrame(prov, fg_color="transparent")
        list_row.pack(fill="x", padx=18, pady=(0, 12))
        self.order_list = ctk.CTkTextbox(
            list_row, height=90, activate_scrollbars=False,
            fg_color=p["card2"], border_width=1, border_color=p["border"],
            text_color=p["text"], corner_radius=10,
        )
        self.order_list.pack(side="left", fill="x", expand=True)
        order = list(settings.get("provider_order") or [])
        self.order_list.insert("1.0", "\n".join(order))
        self.order_list.configure(state="disabled")
        btn_col = ctk.CTkFrame(list_row, fg_color="transparent")
        btn_col.pack(side="right", padx=(10, 0))

        def arrow(text, dy):
            return ctk.CTkButton(
                btn_col, text=text, width=40, height=34, corner_radius=8,
                fg_color=p["card2"], hover_color=p["border"], border_width=1,
                border_color=p["border"], text_color=p["text"],
                command=lambda: self._move(dy),
            )

        arrow("▲", -1).pack(pady=3)
        arrow("▼", 1).pack(pady=3)

        ctk.CTkLabel(
            prov, text="API keys", font=("Segoe UI Semibold", 14),
            text_color=p["text"],
        ).pack(anchor="w", padx=18, pady=(4, 2))
        ctk.CTkLabel(
            prov,
            text="Bring your own key (BYOK) — keys stay on this PC only.\n"
                 "No key is bundled with the app. Stored locally · applied after Save.",
            font=("Segoe UI", 11), text_color=p["muted"],
            justify="left", wraplength=520,
        ).pack(anchor="w", padx=18, pady=(0, 8))

        self.key_entries = {}
        stats_map = settings.get("provider_stats") or {}
        self.stats_labels = {}
        for name in ALL_PROVIDERS:
            row = ctk.CTkFrame(prov, fg_color=p["card2"], corner_radius=10,
                               border_width=1, border_color=p["border"])
            row.pack(fill="x", padx=18, pady=4)
            has = bool(API_KEYS.get(name))
            ctk.CTkLabel(
                row, text="●", text_color=SUCCESS if has else p["border"], width=16,
                font=("Segoe UI", 12),
            ).pack(side="left", padx=(12, 4), pady=8)
            ctk.CTkLabel(
                row, text=PROVIDER_LABELS[name], width=110, anchor="w",
                font=("Segoe UI", 13), text_color=p["text"],
            ).pack(side="left", padx=(0, 4), pady=8)
            var = ctk.StringVar(value=API_KEYS.get(name, ""))
            entry = ctk.CTkEntry(
                row, textvariable=var, show="•", height=34, corner_radius=8,
                fg_color=p["card"], border_color=p["border"], text_color=p["text"],
                placeholder_text="API key (optional)",
            )
            entry.pack(side="left", fill="x", expand=True, padx=(0, 6), pady=8)
            self.key_entries[name] = var
            show_var = ctk.BooleanVar(value=False)

            def toggle(e=entry, sv=show_var):
                e.configure(show="" if sv.get() else "•")

            ctk.CTkCheckBox(
                row, text="Show", width=54, variable=show_var, command=toggle,
                checkbox_width=16, checkbox_height=16, fg_color=ACCENT,
                font=("Segoe UI", 11), text_color=p["muted"],
            ).pack(side="left", padx=(0, 4), pady=8)
            url = PROVIDER_URLS.get(name, "")
            if url:
                ctk.CTkButton(
                    row, text="Get key", width=70, height=34, corner_radius=8,
                    fg_color="transparent", border_width=1, border_color=ACCENT,
                    text_color=ACCENT, hover_color=p["card"],
                    command=lambda u=url: self._open_url(u),
                ).pack(side="left", padx=(0, 4), pady=8)
            ctk.CTkButton(
                row, text="Test", width=50, height=34, corner_radius=8,
                fg_color=ACCENT, hover_color="#3a76e0",
                command=lambda n=name: self._test(n),
            ).pack(side="left", padx=(0, 6), pady=8)
            entry_data = stats_map.get(name) or {}
            if entry_data.get("ok"):
                stat_txt = f"avg {float(entry_data.get('avg', 0) or 0):.1f}s"
                stat_color = SUCCESS
            elif entry_data.get("fail"):
                stat_txt = "failing"
                stat_color = DANGER
            else:
                stat_txt = "—"
                stat_color = p["muted"]
            stat_lbl = ctk.CTkLabel(
                row, text=stat_txt, width=64, anchor="e",
                font=("Segoe UI", 11), text_color=stat_color,
            )
            stat_lbl.pack(side="left", padx=(0, 8), pady=8)
            self.stats_labels[name] = stat_lbl

        self.test_status = ctk.CTkLabel(
            prov, text="", wraplength=520, justify="left",
            font=("Segoe UI", 12), text_color=p["muted"],
        )
        self.test_status.pack(anchor="w", padx=18, pady=(6, 18))

    @staticmethod
    def _open_url(url: str):
        import webbrowser

        try:
            webbrowser.open(url)
        except Exception:
            pass

    def _ordered(self):
        raw = self.order_list.get("1.0", "end")
        items = []
        for line in raw.splitlines():
            v = line.strip().lower()
            if v in ALL_PROVIDERS and v not in items:
                items.append(v)
        for name in ALL_PROVIDERS:
            if name not in items:
                items.append(name)
        return items

    def _move(self, delta):
        items = self._ordered()
        try:
            idx = int(self.order_list.index("insert").split(".")[0]) - 1
        except Exception:
            idx = 0
        idx = max(0, min(len(items) - 1, idx))
        j = idx + delta
        if j < 0 or j >= len(items):
            return
        items[idx], items[j] = items[j], items[idx]
        self.order_list.configure(state="normal")
        self.order_list.delete("1.0", "end")
        self.order_list.insert("1.0", "\n".join(items))
        self.order_list.mark_set("insert", f"{j + 1}.0")
        self.order_list.configure(state="disabled")

    def _test(self, name):
        from llm import test_provider

        def run():
            ok, msg = test_provider(name)

            def done():
                if not self.winfo_exists():
                    return
                self.test_status.configure(
                    text=f"{PROVIDER_LABELS[name]}:  {'OK' if ok else 'FAIL'}  —  {msg}",
                    text_color=SUCCESS if ok else DANGER,
                )

            try:
                self.after(0, done)
            except Exception:
                pass

        self.test_status.configure(text=f"Testing {PROVIDER_LABELS[name]}…")
        threading.Thread(target=run, daemon=True).start()

    def _add_cmd_row(self, name="", prompt=""):
        p = palette()
        row = ctk.CTkFrame(
            self.cmd_list, fg_color=p["card2"], corner_radius=8,
            border_width=1, border_color=p["border"],
        )
        row.pack(fill="x", pady=3)
        name_var = ctk.StringVar(value=name)
        prompt_var = ctk.StringVar(value=prompt)
        ctk.CTkEntry(
            row, textvariable=name_var, width=150, height=32, corner_radius=6,
            fg_color=p["card"], border_color=p["border"], text_color=p["text"],
            placeholder_text="Name",
        ).pack(side="left", padx=(8, 4), pady=6)
        ctk.CTkEntry(
            row, textvariable=prompt_var, height=32, corner_radius=6,
            fg_color=p["card"], border_color=p["border"], text_color=p["text"],
            placeholder_text="Instruction — what should the AI do with the selected text?",
        ).pack(side="left", fill="x", expand=True, padx=(0, 4), pady=6)
        rec = {"name": name_var, "prompt": prompt_var, "row": row}

        def remove(r=rec):
            try:
                r["row"].destroy()
            except Exception:
                pass
            if r in self.cmd_rows:
                self.cmd_rows.remove(r)

        ctk.CTkButton(
            row, text="✕", width=28, height=28, corner_radius=6,
            fg_color="transparent", hover_color=DANGER,
            text_color=p["muted"], command=remove,
        ).pack(side="right", padx=(0, 6), pady=6)
        self.cmd_rows.append(rec)

    def save(self):
        settings = load_settings()
        settings["hotkey"] = (self.hotkey_var.get() or "").strip().lower() or "ctrl+alt+z"
        settings["auto_replace"] = bool(self.auto_var.get())
        settings["enabled"] = bool(self.enabled_var.get())
        settings["auto_update"] = bool(self.auto_update_var.get())
        settings["provider_order"] = self._ordered()
        settings["api_keys"] = {
            name: (var.get() or "").strip() for name, var in self.key_entries.items()
        }
        commands = []
        for rec in self.cmd_rows:
            cname = (rec["name"].get() or "").strip()
            cprompt = (rec["prompt"].get() or "").strip()
            if cname and cprompt:
                commands.append({"name": cname, "prompt": cprompt})
        settings["my_commands"] = commands
        tone_label = self.tone_var.get()
        inv = {v: k for k, v in self._tone_labels.items()}
        settings["tone"] = inv.get(tone_label, "professional")
        settings["translate_to"] = (self.translate_var.get() or "").strip()
        settings["ignore_words"] = [
            w.strip() for w in (self.ignore_var.get() or "").split(",") if w.strip()
        ]
        settings["result_ui"] = (
            "popup" if self.result_ui_var.get() == "Full preview window" else "overlay"
        )
        settings["smart_order"] = bool(self.smart_order_var.get())
        save_settings(settings)
        reload_api_keys()
        self.app.on_settings_saved()
        self.test_status.configure(text="✓ Saved — keys applied, no restart needed",
                                   text_color=SUCCESS)
        try:
            self.app.home.refresh()
        except Exception:
            pass


class HistoryPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        p = palette()

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(10, 6))
        ctk.CTkLabel(header, text="History", font=("Segoe UI Semibold", 22),
                     text_color=p["text"]).pack(side="left")
        ctk.CTkButton(
            header, text="Refresh", width=90, height=36, corner_radius=10,
            fg_color=p["card"], hover_color=p["card2"], border_width=1,
            border_color=p["border"], text_color=p["text"], command=self.reload,
        ).pack(side="right", padx=(0, 8))
        ctk.CTkButton(
            header, text="Clear", width=80, height=36, corner_radius=10,
            fg_color=DANGER, hover_color="#e05555", command=self.clear,
        ).pack(side="right")

        split = ctk.CTkFrame(self, fg_color="transparent")
        split.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        split.columnconfigure(0, weight=1)
        split.columnconfigure(1, weight=1)
        split.rowconfigure(0, weight=1)

        left = Card(split)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        ctk.CTkLabel(left, text="Corrections", font=("Segoe UI Semibold", 13),
                     text_color=p["muted"]).pack(anchor="w", padx=14, pady=(14, 6))
        self.listbox = ctk.CTkTextbox(
            left, activate_scrollbars=True, fg_color=p["card2"],
            border_width=0, text_color=p["text"],
        )
        self.listbox.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.listbox.bind("<ButtonRelease-1>", self._on_select)

        right = Card(split)
        right.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        ctk.CTkLabel(right, text="Detail", font=("Segoe UI Semibold", 13),
                     text_color=p["muted"]).pack(anchor="w", padx=14, pady=(14, 6))
        self.detail = ctk.CTkTextbox(
            right, wrap="word", fg_color=p["card2"], border_width=0, text_color=p["text"],
        )
        self.detail.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self._items = []
        self.reload()

    def reload(self):
        p = palette()
        self._items = history_store.list_items()
        self.listbox.configure(state="normal")
        self.listbox.delete("1.0", "end")
        if not self._items:
            self.listbox.insert("end", "No corrections yet.")
        for i, item in enumerate(self._items):
            preview = (item.get("original") or "").replace("\n", " ")[:60]
            self.listbox.insert("end", f"{i + 1}.  {item.get('time', '')}   {preview}\n")
        self.listbox.configure(state="disabled")
        if self._items:
            self._show(0)
        else:
            self.detail.configure(state="normal")
            self.detail.delete("1.0", "end")
            self.detail.configure(state="disabled")

    def _on_select(self, _event=None):
        try:
            idx = int(self.listbox.index("insert").split(".")[0]) - 1
            if 0 <= idx < len(self._items):
                self._show(idx)
        except Exception:
            pass

    def _show(self, idx):
        item = self._items[idx]
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert(
            "end", f"{item.get('time', '')}   ·   {item.get('provider', '')}\n\n"
        )
        self.detail.insert("end", "── ORIGINAL ──\n")
        self.detail.insert("end", (item.get("original") or "") + "\n\n")
        self.detail.insert("end", "── CORRECTED ──\n")
        self.detail.insert("end", (item.get("corrected") or "") + "\n")
        self.detail.configure(state="disabled")

    def clear(self):
        history_store.clear()
        self.reload()
        try:
            self.app.home.refresh()
        except Exception:
            pass


class AboutPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        p = palette()

        section_title(self, "About", f"Version {VERSION}")

        brand = Card(self)
        brand.pack(fill="x", padx=10, pady=(0, 12))
        row = ctk.CTkFrame(brand, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(20, 0))
        ctk.CTkLabel(
            row, text="✦", font=("Segoe UI", 36), text_color=ACCENT
        ).pack(side="left", padx=(0, 14))
        info = ctk.CTkFrame(row, fg_color="transparent")
        info.pack(side="left")
        ctk.CTkLabel(info, text="TextMate AI", font=("Segoe UI Semibold", 20),
                     text_color=p["text"]).pack(anchor="w")
        ctk.CTkLabel(info, text="Universal desktop grammar assistant",
                     font=("Segoe UI", 13), text_color=p["muted"]).pack(anchor="w")
        ctk.CTkLabel(
            brand,
            text="Works in Word, Excel, browsers, Notepad — any Windows app.\n"
                 "Bring your own free LLM key (Groq, Gemini, …). "
                 "No key bundled. No telemetry. No Office plugins.",
            font=("Segoe UI", 13), text_color=p["muted"], justify="left",
            wraplength=520,
        ).pack(anchor="w", padx=20, pady=(14, 8))

        ctk.CTkLabel(
            brand,
            text="Developed by Pranjit Das",
            font=("Segoe UI Semibold", 13), text_color=ACCENT, justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 4))

        ctk.CTkLabel(
            brand,
            text="v" + VERSION + " · Proprietary free software · See LICENSE & PRIVACY.md",
            font=("Segoe UI", 11), text_color=p["muted"], justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 4))

        link_row = ctk.CTkFrame(brand, fg_color="transparent")
        link_row.pack(anchor="w", padx=20, pady=(0, 20))

        def open_doc(filename):
            import os as _os
            import webbrowser as _wb
            import sys as _sys

            candidates = []
            if getattr(_sys, "frozen", False):
                candidates.append(_os.path.join(_os.path.dirname(_sys.executable), filename))
            candidates.extend([
                _os.path.join(_os.getcwd(), filename),
                filename,
            ])
            target = next((c for c in candidates if _os.path.isfile(c)), filename)
            _wb.open("file:///" + _os.path.abspath(target).replace("\\", "/"))

        ctk.CTkButton(
            link_row, text="License", width=90, height=32, corner_radius=8,
            fg_color="transparent", border_width=1, border_color=p["border"],
            text_color=ACCENT, hover_color=p["card2"],
            command=lambda: open_doc("LICENSE"),
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            link_row, text="Privacy policy", width=110, height=32, corner_radius=8,
            fg_color="transparent", border_width=1, border_color=p["border"],
            text_color=ACCENT, hover_color=p["card2"],
            command=lambda: open_doc("PRIVACY.md"),
        ).pack(side="left")

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", padx=10, pady=(0, 12))

        ctk.CTkButton(
            actions, text="Replay guide", width=140, height=38, fg_color=ACCENT,
            hover_color="#3a76e0", corner_radius=10,
            font=("Segoe UI Semibold", 13),
            command=lambda: app.show_page("guide"),
        ).pack(side="left", padx=(0, 8))

        self.update_status = ctk.StringVar(value="")
        self.check_btn = ctk.CTkButton(
            actions, text="Check for updates", width=150, height=38,
            fg_color=p["card"], hover_color=p["card2"], border_width=1,
            border_color=p["border"], text_color=p["text"], corner_radius=10,
            command=self._check_updates,
        )
        self.check_btn.pack(side="left", padx=(0, 8))

        ctk.CTkLabel(
            actions, textvariable=self.update_status,
            font=("Segoe UI", 12), text_color=p["muted"],
        ).pack(side="left")

        tips = Card(self)
        tips.pack(fill="x", padx=10)
        ctk.CTkLabel(tips, text="Tips", font=("Segoe UI Semibold", 14),
                     text_color=p["text"]).pack(anchor="w", padx=18, pady=(16, 6))
        ctk.CTkLabel(
            tips,
            text="• Select text first, then press the hotkey\n"
                 "• Double-click the tray icon to reopen this window\n"
                 "• Close button hides to tray — app keeps running",
            font=("Segoe UI", 13), text_color=p["muted"], justify="left",
        ).pack(anchor="w", padx=18, pady=(0, 18))

    def _check_updates(self):
        import updater

        self.check_btn.configure(state="disabled")
        self.update_status.set("Checking…")

        def done(info):
            def apply_result():
                try:
                    self.check_btn.configure(state="normal")
                except Exception:
                    pass
                if isinstance(info, Exception):
                    self.update_status.set(f"Check failed: {info}")
                    return
                if not info:
                    self.update_status.set(f"✓ Up to date (v{VERSION})")
                    return
                self.update_status.set(f"v{info['version']} available")
                show_update_dialog(self, info)

            try:
                self.after(0, apply_result)
            except Exception:
                pass

        updater.check_async(done)


class UpdateDialog(ctk.CTkToplevel):
    def __init__(self, master, info: dict):
        super().__init__(master)
        p = palette()
        self.title("Update available")
        self.geometry("520x360")
        self.minsize(440, 300)
        self.configure(fg_color=p["bg"])
        self.attributes("-topmost", True)
        self.info = info
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.after(150, self.focus_force)

        ctk.CTkLabel(
            self, text=f"Update {info.get('version', '?')} available",
            font=("Segoe UI Semibold", 18), text_color=p["text"],
        ).pack(anchor="w", padx=20, pady=(20, 4))
        ctk.CTkLabel(
            self, text=f"You have v{VERSION}",
            font=("Segoe UI", 13), text_color=p["muted"],
        ).pack(anchor="w", padx=20, pady=(0, 10))

        notes = (info.get("notes") or "").strip()[:600] or "No release notes."
        box = ctk.CTkTextbox(
            self, height=120, wrap="word", fg_color=p["card2"],
            border_width=1, border_color=p["border"], text_color=p["text"],
        )
        box.pack(fill="x", padx=20)
        box.insert("1.0", notes)
        box.configure(state="disabled")

        self.progress = ctk.CTkProgressBar(self, height=8, progress_color=ACCENT)
        self.progress.pack(fill="x", padx=20, pady=(12, 4))
        self.progress.set(0)
        self.status = ctk.CTkLabel(
            self, text="", font=("Segoe UI", 12), text_color=p["muted"],
        )
        self.status.pack(anchor="w", padx=20)

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(16, 20))

        self.later_btn = ctk.CTkButton(
            row, text="Later", width=90, height=36, fg_color=p["card"],
            border_width=1, border_color=p["border"], text_color=p["text"],
            hover_color=p["card2"], corner_radius=10, command=self.destroy,
        )
        self.later_btn.pack(side="right", padx=(8, 0))

        self.update_btn = ctk.CTkButton(
            row, text="Update & restart", width=150, height=36, fg_color=ACCENT,
            hover_color="#3a76e0", corner_radius=10,
            font=("Segoe UI Semibold", 13), command=self._start_update,
        )
        self.update_btn.pack(side="right")

        if info.get("needs_manual"):
            self.update_btn.configure(text="Open release page", command=self._open_page)

    def _open_page(self):
        import updater

        updater.open_release_page()
        self.destroy()

    def _start_update(self):
        import updater

        if self.info.get("needs_manual"):
            self._open_page()
            return
        if not updater.is_frozen():
            self.status.configure(
                text="Dev mode — rebuild exe to test install. Opening release…",
            )
            updater.open_release_page()
            return
        self.update_btn.configure(state="disabled")
        self.later_btn.configure(state="disabled")
        self.status.configure(text="Downloading…")

        info = self.info

        def progress(done, total):
            def apply():
                try:
                    self.progress.set(done / max(1, total))
                    self.status.configure(
                        text=f"Downloading… {done * 100 // max(1, total)}%"
                    )
                except Exception:
                    pass

            try:
                self.after(0, apply)
            except Exception:
                pass

        def run():
            try:
                new_exe = updater.download_update(info, progress_cb=progress)

                def apply():
                    try:
                        self.status.configure(text="Installing… restarting")
                        self.progress.set(1)
                    except Exception:
                        pass
                    try:
                        updater.apply_update_and_restart(new_exe)
                    except Exception as exc:
                        self.update_btn.configure(state="normal")
                        self.later_btn.configure(state="normal")
                        self.status.configure(text=f"Install failed: {exc}")

                self.after(0, apply)
            except Exception as exc:
                def fail():
                    self.update_btn.configure(state="normal")
                    self.later_btn.configure(state="normal")
                    self.status.configure(text=f"Download failed: {exc}")

                try:
                    self.after(0, fail)
                except Exception:
                    pass

        threading.Thread(target=run, daemon=True).start()


def show_update_dialog(master, info: dict):
    try:
        return UpdateDialog(master, info)
    except Exception:
        return None


ALL_PROVIDERS = list(PROVIDER_LABELS.keys())


def is_app_activated() -> bool:
    from license import is_valid_license_key

    key = get("license_key") or ""
    if not key:
        return False
    if not is_valid_license_key(key):
        return False
    return bool(get("activated", False))


def activate_with_key(key: str) -> bool:
    from license import is_valid_license_key

    if not is_valid_license_key(key):
        return False
    settings = load_settings()
    settings["activated"] = True
    settings["license_key"] = key.strip().upper()
    save_settings(settings)
    return True


class SetupWizard(ctk.CTkFrame):
    """First-run 3-step wizard: pick provider → paste key & test → done."""

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.step = 0
        p = palette()

        wrap = ctk.CTkFrame(self, fg_color="transparent")
        wrap.place(relx=0.5, rely=0.5, anchor="center")
        card = Card(wrap, width=520, corner_radius=16)
        card.pack(padx=20, pady=20)
        card.pack_propagate(False)

        ctk.CTkLabel(
            card, text="✦", font=("Segoe UI", 30), text_color=ACCENT
        ).pack(pady=(24, 4))
        self.step_badge = badge(card, "STEP 1 OF 3", ACCENT)
        self.step_badge.pack(pady=(0, 8))
        self.title_lbl = ctk.CTkLabel(
            card, text="", font=("Segoe UI Semibold", 19), text_color=p["text"]
        )
        self.title_lbl.pack(pady=(0, 6))
        self.body_lbl = ctk.CTkLabel(
            card, text="", font=("Segoe UI", 13), text_color=p["muted"],
            justify="center", wraplength=440,
        )
        self.body_lbl.pack(pady=(0, 14))

        # Step 0 controls
        self.pick_frame = ctk.CTkFrame(card, fg_color="transparent")
        labels = [PROVIDER_LABELS[n] for n in ALL_PROVIDERS]
        self._label_to_name = {PROVIDER_LABELS[n]: n for n in ALL_PROVIDERS}
        self.provider_var = ctk.StringVar(value="Groq")
        ctk.CTkOptionMenu(
            self.pick_frame, variable=self.provider_var, values=labels,
            width=260, height=38, corner_radius=10, fg_color=p["card2"],
            button_color=p["border"], button_hover_color=p["sidebar_hover"],
            text_color=p["text"], font=("Segoe UI", 13),
        ).pack(pady=(0, 8))
        ctk.CTkButton(
            self.pick_frame, text="Get a free key ↗", width=200, height=36,
            fg_color="transparent", border_width=1, border_color=ACCENT,
            text_color=ACCENT, hover_color=p["card2"], corner_radius=10,
            command=self._open_key_page,
        ).pack()

        # Step 1 controls
        self.key_frame = ctk.CTkFrame(card, fg_color="transparent")
        self.key_entry = ctk.CTkEntry(
            self.key_frame, width=400, height=42, corner_radius=10,
            fg_color=p["card2"], border_color=p["border"], text_color=p["text"],
            show="•", font=("Consolas", 13),
            placeholder_text="Paste your API key",
        )
        self.key_entry.pack(pady=(0, 8))
        self.key_entry.bind("<Return>", lambda e: self._test_and_next())
        show_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            self.key_frame, text="Show key", variable=show_var,
            checkbox_width=16, checkbox_height=16, fg_color=ACCENT,
            font=("Segoe UI", 11), text_color=p["muted"],
            command=lambda: self.key_entry.configure(
                show="" if show_var.get() else "•"
            ),
        ).pack(anchor="w")
        self.key_status = ctk.CTkLabel(
            self.key_frame, text="", font=("Segoe UI", 12),
            text_color=DANGER, wraplength=420,
        )
        self.key_status.pack(pady=(6, 0))

        # Step 2 controls
        self.done_frame = ctk.CTkFrame(card, fg_color="transparent")
        ctk.CTkLabel(
            self.done_frame, text="✓", font=("Segoe UI", 34), text_color=SUCCESS
        ).pack()
        ctk.CTkLabel(
            self.done_frame,
            text=f"Press {get('hotkey') or 'ctrl+alt+z'} on selected text\nto proofread anywhere.",
            font=("Segoe UI", 13), text_color=p["muted"], justify="center",
        ).pack(pady=(4, 0))

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=24, pady=(16, 6))
        self.back_btn = ctk.CTkButton(
            btn_row, text="Back", width=90, height=38,
            fg_color="transparent", border_width=1, border_color=p["border"],
            text_color=p["muted"], hover_color=p["card2"], corner_radius=10,
            command=self._back,
        )
        self.back_btn.pack(side="left", padx=(0, 8))
        self.next_btn = ctk.CTkButton(
            btn_row, text="Continue", width=150, height=38,
            fg_color=ACCENT, hover_color="#3a76e0", corner_radius=10,
            font=("Segoe UI Semibold", 13), command=self._next,
        )
        self.next_btn.pack(side="right")
        ctk.CTkButton(
            card, text="Skip for now", width=120, height=30,
            fg_color="transparent", hover_color=p["card"],
            text_color=p["muted"], font=("Segoe UI", 12),
            command=lambda: self.app.finish_wizard(),
        ).pack(pady=(2, 16))

        self.render()

    # --- steps ---
    def render(self):
        p = palette()
        self.pick_frame.pack_forget()
        self.key_frame.pack_forget()
        self.done_frame.pack_forget()
        self.step_badge.configure(text=f"STEP {self.step + 1} OF 3")
        if self.step == 0:
            self.title_lbl.configure(text="Choose your AI provider")
            self.body_lbl.configure(
                text="The app needs one free API key (bring your own key). "
                     "Groq is recommended — fast and free."
            )
            self.pick_frame.pack()
            self.back_btn.configure(state="disabled")
            self.next_btn.configure(text="Continue", command=self._next)
        elif self.step == 1:
            name = self._label_to_name.get(self.provider_var.get(), "groq")
            self.title_lbl.configure(text=f"Paste your {PROVIDER_LABELS[name]} key")
            self.body_lbl.configure(
                text="Your key stays on this PC only — never uploaded "
                     "anywhere except the provider itself."
            )
            self.key_status.configure(text="", text_color=DANGER)
            self.key_frame.pack()
            self.back_btn.configure(state="normal")
            self.next_btn.configure(text="Test & continue", command=self._test_and_next)
        else:
            self.title_lbl.configure(text="You're all set!")
            self.body_lbl.configure(
                text="Setup complete. Everything runs quietly in the tray."
            )
            self.done_frame.pack()
            self.back_btn.configure(state="disabled")
            self.next_btn.configure(text="Finish", command=lambda: self.app.finish_wizard())

    def _next(self):
        self.step = min(2, self.step + 1)
        self.render()

    def _back(self):
        self.step = max(0, self.step - 1)
        self.render()

    def _open_key_page(self):
        name = self._label_to_name.get(self.provider_var.get(), "groq")
        url = PROVIDER_URLS.get(name, "")
        if url:
            import webbrowser

            try:
                webbrowser.open(url)
            except Exception:
                pass

    def _test_and_next(self):
        from llm import test_provider

        name = self._label_to_name.get(self.provider_var.get(), "groq")
        key = (self.key_entry.get() or "").strip()
        if not key:
            self.key_status.configure(text="Paste your API key first.")
            return
        self.next_btn.configure(state="disabled", text="Testing…")
        self.key_status.configure(text="", text_color=DANGER)

        def run():
            settings = load_settings()
            keys = dict(settings.get("api_keys") or {})
            keys[name] = key
            settings["api_keys"] = keys
            save_settings(settings)
            reload_api_keys()
            ok, msg = test_provider(name)

            def done():
                if not self.winfo_exists():
                    return
                self.next_btn.configure(state="normal", text="Test & continue")
                if ok:
                    self.step = 2
                    self.render()
                else:
                    self.key_status.configure(text=f"Test failed — {msg}")

            try:
                self.after(0, done)
            except Exception:
                pass

        threading.Thread(target=run, daemon=True).start()


class ActivationPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        p = palette()
        self.configure(fg_color=p["bg"])

        wrap = ctk.CTkFrame(self, fg_color="transparent")
        wrap.place(relx=0.5, rely=0.5, anchor="center")

        card = Card(wrap, width=460, corner_radius=16)
        card.pack(padx=20, pady=20)
        card.pack_propagate(False)

        ctk.CTkLabel(
            card, text="✦", font=("Segoe UI", 34), text_color=ACCENT
        ).pack(pady=(28, 6))
        ctk.CTkLabel(
            card,
            text="Activate TextMate AI",
            font=("Segoe UI Semibold", 20),
            text_color=p["text"],
        ).pack(pady=(0, 6))
        ctk.CTkLabel(
            card,
            text="Enter your access key to unlock proofreading.\nWorks offline — no account required.",
            font=("Segoe UI", 13),
            text_color=p["muted"],
            justify="center",
        ).pack(pady=(0, 18))

        self.entry = ctk.CTkEntry(
            card,
            width=360,
            height=44,
            placeholder_text="APRO-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX",
            font=("Consolas", 13),
            corner_radius=10,
            fg_color=p["card2"],
            border_color=p["border"],
            text_color=p["text"],
        )
        self.entry.pack(pady=(0, 10))
        self.entry.bind("<Return>", lambda e: self._submit())

        self.status = ctk.CTkLabel(
            card, text="", font=("Segoe UI", 12), text_color=DANGER
        )
        self.status.pack(pady=(0, 12))

        self.btn = ctk.CTkButton(
            card,
            text="Activate",
            command=self._submit,
            width=200,
            height=42,
            fg_color=ACCENT,
            hover_color="#3a76e0",
            corner_radius=10,
            font=("Segoe UI Semibold", 14),
        )
        self.btn.pack(pady=(0, 8))

        ctk.CTkButton(
            card,
            text="Quit",
            command=self.app.app_callbacks["quit"],
            width=200,
            height=36,
            fg_color="transparent",
            border_width=1,
            border_color=p["border"],
            text_color=p["muted"],
            hover_color=p["card2"],
            corner_radius=10,
        ).pack(pady=(0, 24))

        self.entry.focus_set()

    def _submit(self):
        key = self.entry.get().strip()
        if not key:
            self.status.configure(text="Enter an access key.")
            return
        if not activate_with_key(key):
            self.status.configure(text="Invalid access key. Check and try again.")
            return
        self.status.configure(text="")
        self.app.on_activated()


class MainWindow(ctk.CTk):
    def __init__(self, app_callbacks):
        super().__init__()
        self.app_callbacks = app_callbacks
        self.title("TextMate AI")
        self.geometry("960x660")
        self.minsize(860, 580)
        self._current_page = "home"
        self._sidebar = None
        self._rebuilding = False
        self._activated = is_app_activated()
        apply_theme()
        p = palette()
        self.configure(fg_color=p["bg"])

        if not self._activated:
            self._build_activation_shell()
        else:
            self._build_shell()
            self._route_initial()

    def _build_activation_shell(self):
        p = palette()
        # Minimal shell: no sidebar nav until activated
        self._sidebar = None
        self.content = ctk.CTkFrame(self, corner_radius=0, fg_color=p["bg"])
        self.content.pack(fill="both", expand=True)
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)
        self.pages = {}
        self.home = None
        self.activation = ActivationPage(self.content, self)
        self.pages["activation"] = self.activation
        self.activation.grid(row=0, column=0, sticky="nsew")
        self.activation.tkraise()
        self.nav_buttons = {}
        self.protocol("WM_DELETE_WINDOW", self.app_callbacks["quit"])

    def on_activated(self):
        self._activated = True
        # Rebuild full UI shell now that license is valid
        try:
            for child in self.winfo_children():
                child.destroy()
        except Exception:
            pass
        self._build_shell()
        self._route_initial()
        try:
            self.app_callbacks.get("on_activated")()
        except Exception:
            pass

    def preview_theme(self, mode: str) -> None:
        pass

    def rebuild_theme(self) -> None:
        pass

    def _build_shell(self):
        p = palette()
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        side = ctk.CTkFrame(self, width=220, corner_radius=0, fg_color=p["sidebar"])
        side.grid(row=0, column=0, sticky="nsew")
        side.grid_propagate(False)
        self._sidebar = side

        brand = ctk.CTkFrame(side, fg_color="transparent")
        brand.pack(fill="x", padx=18, pady=(22, 20))
        icon = ctk.CTkLabel(brand, text="✦", font=("Segoe UI", 22), text_color=ACCENT)
        icon.pack(side="left", padx=(0, 10))
        texts = ctk.CTkFrame(brand, fg_color="transparent")
        texts.pack(side="left")
        ctk.CTkLabel(
            texts, text="TextMate AI", font=("Segoe UI Semibold", 15),
            text_color="white", anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            texts, text=f"v{VERSION}", font=("Segoe UI", 11), text_color="#6e7a94",
            anchor="w",
        ).pack(anchor="w")

        nav_items = [
            ("home", "◈", "Dashboard"),
            ("guide", "◇", "How it works"),
            ("settings", "⚙", "Settings"),
            ("history", "☰", "History"),
            ("about", "ⓘ", "About"),
        ]
        self.nav_buttons = {}
        for key, icon_ch, label in nav_items:
            btn = ctk.CTkButton(
                side,
                text=f"  {icon_ch}    {label}",
                anchor="w",
                height=42,
                corner_radius=10,
                fg_color="transparent",
                hover_color=p["sidebar_hover"],
                text_color=p["sidebar_text"],
                font=("Segoe UI", 13),
                command=lambda k=key: self.show_page(k),
            )
            btn.pack(fill="x", padx=12, pady=3)
            self.nav_buttons[key] = btn

        bottom = ctk.CTkFrame(side, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=14, pady=14)
        ctk.CTkButton(
            bottom, text="Hide to tray", height=38, corner_radius=10,
            fg_color=p["sidebar_hover"], hover_color="#243252",
            text_color=p["sidebar_text"],
            command=self.hide_to_tray,
        ).pack(fill="x", pady=(0, 8))
        ctk.CTkButton(
            bottom, text="Quit", height=38, corner_radius=10,
            fg_color="transparent", border_width=1, border_color="#ff5c5c",
            text_color="#ff7b7b", hover_color="#2a1520",
            command=self.app_callbacks["quit"],
        ).pack(fill="x")

        self.content = ctk.CTkFrame(self, corner_radius=0, fg_color=p["bg"])
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

        self.pages = {}
        self.home = HomePage(self.content, self)
        self.pages["home"] = self.home
        self.pages["guide"] = GuidePage(self.content, self)
        self.pages["settings"] = SettingsPage(self.content, self)
        self.pages["history"] = HistoryPage(self.content, self)
        self.pages["about"] = AboutPage(self.content, self)
        self.pages["setup"] = SetupWizard(self.content, self)
        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")

        self.protocol("WM_DELETE_WINDOW", self.hide_to_tray)

    def _needs_wizard(self) -> bool:
        if bool(get("wizard_done", False)):
            return False
        try:
            from llm import available_providers

            return not available_providers()
        except Exception:
            return True

    def _route_initial(self):
        if self._needs_wizard():
            self.show_page("setup")
            return
        first = not bool(get("onboarded", False))
        self.show_page("guide" if first else "home")

    def finish_wizard(self):
        settings = load_settings()
        settings["wizard_done"] = True
        save_settings(settings)
        first = not bool(get("onboarded", False))
        self.show_page("guide" if first else "home")

    def show_page(self, key: str):
        p = palette()
        if not self._activated:
            # Only activation page exists
            page = self.pages.get("activation")
            if page:
                page.tkraise()
            return
        page = self.pages.get(key)
        if not page:
            return
        self._current_page = key
        page.tkraise()
        for k, btn in self.nav_buttons.items():
            if k == key:
                btn.configure(
                    fg_color=ACCENT, text_color="white", hover_color="#3a76e0"
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    text_color=p["sidebar_text"],
                    hover_color=p["sidebar_hover"],
                )
        if key == "home":
            self.home.refresh()
        if key == "history":
            try:
                page.reload()
            except Exception:
                pass

    def set_enabled(self, enabled: bool):
        self.app_callbacks["set_enabled"](enabled)
        self.home.refresh()

    def on_settings_saved(self):
        self.app_callbacks["on_settings_saved"]()

    def complete_onboarding(self):
        settings = load_settings()
        settings["onboarded"] = True
        save_settings(settings)
        self.show_page("home")

    def hide_to_tray(self):
        self.app_callbacks["hide_to_tray"]()

    def show_from_tray(self):
        self.deiconify()
        self.lift()
        self.focus_force()
        if self._activated:
            self.show_page("home")
