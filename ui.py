import threading

import customtkinter as ctk

import history as history_store
from config import (
    PROVIDER_LABELS,
    PROVIDER_URLS,
    VERSION,
    API_KEYS,
    get,
    load_settings,
    reload_api_keys,
    save_settings,
)

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


class Popup(ctk.CTkToplevel):
    def __init__(self, master, original, corrected, on_replace, on_copy, provider=""):
        super().__init__(master)
        p = palette()
        self.title("AI Proofreader")
        self.geometry("680x560")
        self.minsize(500, 420)
        self.configure(fg_color=p["bg"])
        self.attributes("-topmost", True)
        self.after(150, self.focus_force)
        self._on_replace = on_replace
        self._on_copy = on_copy
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=18, pady=(16, 6))
        left = ctk.CTkFrame(header, fg_color="transparent")
        left.pack(side="left")
        ctk.CTkLabel(left, text="Proofread Result", font=("Segoe UI Semibold", 18), text_color=p["text"]).pack(
            anchor="w"
        )
        if provider:
            badge(header, PROVIDER_LABELS.get(provider, provider), ACCENT).pack(side="right")

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
        labeled(corr_card, "CORRECTED")
        corrected_box = ctk.CTkTextbox(
            corr_card, height=130, wrap="word", fg_color=p["card2"],
            border_width=0, text_color=p["text"]
        )
        corrected_box.pack(fill="x", padx=12, pady=(0, 12))
        corrected_box.insert("1.0", corrected)
        corrected_box.configure(state="disabled")

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=18, pady=(4, 18))

        ctk.CTkButton(
            btns, text="Replace", command=self._replace, width=150, height=40,
            fg_color=ACCENT, hover_color="#3a76e0", corner_radius=10,
            font=("Segoe UI Semibold", 13),
        ).pack(side="left", padx=(0, 10))
        ctk.CTkButton(
            btns, text="Copy", command=self._copy, width=110, height=40,
            fg_color=p["card2"], hover_color=p["border"], border_width=1,
            border_color=p["border"], text_color=p["text"], corner_radius=10,
        ).pack(side="left", padx=10)
        ctk.CTkButton(
            btns, text="Cancel", command=self.destroy, width=110, height=40,
            fg_color="transparent", hover_color=p["border"], border_width=1,
            border_color=p["border"], text_color=p["muted"], corner_radius=10,
        ).pack(side="left", padx=10)

        ctk.CTkLabel(
            btns, text="Enter = Replace   ·   Esc = Cancel",
            font=("Segoe UI", 11), text_color=p["muted"]
        ).pack(side="right")

        self.bind("<Return>", lambda e: self._replace())
        self.bind("<Escape>", lambda e: self.destroy())

    def _replace(self):
        cb = self._on_replace
        self.destroy()
        cb()

    def _copy(self):
        cb = self._on_copy
        self.destroy()
        cb()


class LoadingPopup(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        p = palette()
        self.title("AI Proofreader")
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
        ctk.CTkLabel(card, text="AI Proofreader", font=("Segoe UI", 11), text_color=p["muted"]).pack(
            pady=(18, 4)
        )
        self._label = ctk.CTkLabel(
            card, text="Checking text", font=("Segoe UI Semibold", 15), text_color=p["text"]
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
    win.title("AI Proofreader")
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
     "body": "Free LLM providers correct grammar, sentence case, and professional tone — with automatic fallback."},
    {"n": "04", "title": "Review & replace",
     "body": "A clean popup shows original vs corrected. Press Enter to Replace, or Copy / Cancel."},
    {"n": "05", "title": "Setup — Get a free API key",
     "body": "Open Settings → Providers → click \"Get key\" next to Groq (or Gemini / NVIDIA / DeepSeek). "
             "Create a free account and copy your API key. Groq is recommended — fast and free. "
             "You bring your own key; nothing is bundled with the app."},
    {"n": "06", "title": "Setup — Paste key & Save",
     "body": "Back in Settings → Providers, paste the key into the provider field, click Test (optional), "
             "then Save changes. No restart needed — the hotkey works immediately."},
    {"n": "07", "title": "Runs quietly in the tray",
     "body": "Close the window to hide to tray. Reopen anytime by double-clicking the tray icon. "
             "App keeps listening for the hotkey in the background."},
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
        ).pack(anchor="w", padx=18, pady=(6, 18))

        prov = Card(scroll)
        prov.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(prov, text="Providers", font=("Segoe UI Semibold", 15),
                     text_color=p["text"]).pack(anchor="w", padx=18, pady=(16, 4))
        ctk.CTkLabel(prov, text="Fallback order — first with a key wins",
                     font=("Segoe UI", 12), text_color=p["muted"]).pack(
            anchor="w", padx=18, pady=(0, 8)
        )

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
            ).pack(side="left", padx=(0, 10), pady=8)

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
        ctk.CTkLabel(info, text="AI Proofreader", font=("Segoe UI Semibold", 20),
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
            text="Activate AI Proofreader",
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
        super().__init__(master=None)
        self.app_callbacks = app_callbacks
        self.title("AI Proofreader")
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
            first = not bool(get("onboarded", False))
            self.show_page("guide" if first else "home")

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
        first = not bool(get("onboarded", False))
        self.show_page("guide" if first else "home")
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
            texts, text="AI Proofreader", font=("Segoe UI Semibold", 15),
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
        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")

        self.protocol("WM_DELETE_WINDOW", self.hide_to_tray)

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
