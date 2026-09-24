import ctypes
import logging
import logging.handlers
import os
import queue
import sys
import threading
import time

import keyboard
import pyperclip
import pystray
from PIL import Image, ImageDraw

import config
import history as history_store
import llm
from config import VERSION, get, load_settings, log_file
from llm import available_providers, check_text

log = logging.getLogger("proofreader")

ENABLED = True
_busy = False
_root = None
_loading = None
_icon = None
_hotkey_hook = None
_ui_queue = queue.Queue()


def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    fh = logging.handlers.RotatingFileHandler(
        log_file(), maxBytes=512_000, backupCount=2, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    if not getattr(sys, "frozen", False):
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        logger.addHandler(sh)


def ui(fn, *args, **kwargs):
    _ui_queue.put((fn, args, kwargs))


def _pump_ui():
    while True:
        try:
            fn, args, kwargs = _ui_queue.get_nowait()
        except queue.Empty:
            break
        try:
            fn(*args, **kwargs)
        except Exception:
            log.exception("UI task failed")
    if _root is not None:
        try:
            _root.after(50, _pump_ui)
        except Exception:
            pass


def acquire_single_instance():
    if sys.platform != "win32":
        return True
    ctypes.windll.kernel32.CreateMutexW(None, False, "AIProofreader_SingleInstance")
    return ctypes.windll.kernel32.GetLastError() != 183


def _get_foreground():
    if sys.platform != "win32":
        return None
    return ctypes.windll.user32.GetForegroundWindow()


def _clipboard_seq():
    if sys.platform != "win32":
        return 0
    return ctypes.windll.user32.GetClipboardSequenceNumber()


def _set_foreground(hwnd):
    if not hwnd or sys.platform != "win32":
        return False
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    if user32.GetForegroundWindow() == hwnd:
        return True

    # ALT trick unlocks SetForegroundWindow for this process
    VK_MENU = 0x12
    KEYEVENTF_KEYUP = 0x0002
    user32.keybd_event(VK_MENU, 0, 0, 0)
    try:
        fg = user32.GetForegroundWindow()
        tid_fg = user32.GetWindowThreadProcessId(fg, None) if fg else 0
        tid_cur = kernel32.GetCurrentThreadId()
        attached = False
        if tid_fg and tid_fg != tid_cur:
            attached = bool(user32.AttachThreadInput(tid_cur, tid_fg, True))
        try:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            user32.SetActiveWindow(hwnd)
            user32.SetFocus(hwnd)
        finally:
            if attached:
                user32.AttachThreadInput(tid_cur, tid_fg, False)
    finally:
        user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)

    for _ in range(12):
        if user32.GetForegroundWindow() == hwnd:
            time.sleep(0.06)
            return True
        time.sleep(0.03)
        user32.SetForegroundWindow(hwnd)
    ok = user32.GetForegroundWindow() == hwnd
    time.sleep(0.06)
    return bool(ok)


def _wait_modifiers_up(timeout=0.7):
    if sys.platform != "win32":
        time.sleep(0.12)
        return
    user32 = ctypes.windll.user32
    keys = (0x10, 0x11, 0x12, 0x5B, 0x5C)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not any(user32.GetAsyncKeyState(v) & 0x8000 for v in keys):
            break
        time.sleep(0.02)
    for vk in keys:
        if user32.GetAsyncKeyState(vk) & 0x8000:
            user32.keybd_event(vk, 0, 0x0002, 0)
    time.sleep(0.05)


def _read_clipboard():
    try:
        value = pyperclip.paste()
        if isinstance(value, str):
            return value
    except Exception:
        pass
    if sys.platform != "win32":
        return ""
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    CF_UNICODETEXT = 13
    if not user32.OpenClipboard(None):
        return ""
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return ""
        try:
            return ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def _send_copy():
    if sys.platform == "win32":
        user32 = ctypes.windll.user32
        VK_SHIFT, VK_CONTROL, VK_MENU = 0x10, 0x11, 0x12
        deadline = time.time() + 0.6
        while time.time() < deadline:
            down = [
                user32.GetAsyncKeyState(v) & 0x8000
                for v in (VK_SHIFT, VK_CONTROL, VK_MENU, 0x5B, 0x5C)
            ]
            if not any(down):
                break
            time.sleep(0.02)
        for vk in (VK_SHIFT, VK_MENU, 0x5B, 0x5C):
            user32.keybd_event(vk, 0, 0x0002, 0)
        time.sleep(0.05)

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", ctypes.c_ushort),
                ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_uint),
                ("time", ctypes.c_uint),
                ("dwExtraInfo", ctypes.c_size_t),
            ]

        class INPUT(ctypes.Structure):
            class _I(ctypes.Union):
                _fields_ = [("ki", KEYBDINPUT)]

            _anonymous_ = ("i",)
            _fields_ = [("type", ctypes.c_uint), ("i", _I)]

        INPUT_KEYBOARD = 1
        KEYEVENTF_KEYUP = 0x0002
        inputs = (INPUT * 4)(
            INPUT(INPUT_KEYBOARD, ki=KEYBDINPUT(VK_CONTROL, 0, 0, 0, 0)),
            INPUT(INPUT_KEYBOARD, ki=KEYBDINPUT(0x43, 0, 0, 0, 0)),
            INPUT(INPUT_KEYBOARD, ki=KEYBDINPUT(0x43, 0, KEYEVENTF_KEYUP, 0, 0)),
            INPUT(INPUT_KEYBOARD, ki=KEYBDINPUT(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0, 0)),
        )
        user32.SendInput(4, ctypes.byref(inputs), ctypes.sizeof(INPUT))
    else:
        keyboard.send("ctrl+c")


def _write_clipboard(text: str) -> bool:
    try:
        pyperclip.copy(text)
        if _read_clipboard() == text:
            return True
    except Exception:
        pass
    if sys.platform != "win32":
        return False
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002
    if not user32.OpenClipboard(None):
        return False
    try:
        user32.EmptyClipboard()
        data = (text + "\0").encode("utf-16-le")
        h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not h:
            return False
        ptr = kernel32.GlobalLock(h)
        if not ptr:
            kernel32.GlobalFree(h)
            return False
        ctypes.memmove(ptr, data, len(data))
        kernel32.GlobalUnlock(h)
        if not user32.SetClipboardData(CF_UNICODETEXT, h):
            kernel32.GlobalFree(h)
            return False
        return True
    finally:
        user32.CloseClipboard()


def _is_our_window(hwnd) -> bool:
    if not hwnd or sys.platform != "win32":
        return True
    pid = ctypes.c_ulong(0)
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value == os.getpid()


def capture_selected_text(pre_fg=None):
    original_clip = _read_clipboard()
    seq0 = _clipboard_seq()
    fg = pre_fg or _get_foreground()
    if _is_our_window(fg):
        # Fallback: previous non-our window is unknown; still try restore later
        log.warning("foreground was our window at capture start")

    _wait_modifiers_up(0.7)
    focused = False
    if fg and not _is_our_window(fg):
        focused = _set_foreground(fg)
    time.sleep(0.1)

    captured = ""
    attempts = 0
    for attempt in range(4):
        attempts = attempt + 1
        if fg and not _is_our_window(fg):
            if _get_foreground() != fg:
                focused = _set_foreground(fg)
                time.sleep(0.08)
            else:
                focused = True

        actual_fg = _get_foreground()
        log.info(
            "capture attempt=%d fg_match=%s our_window=%s",
            attempt + 1,
            actual_fg == fg,
            _is_our_window(actual_fg),
        )

        # Only send Ctrl+C when target window actually has focus
        if fg and actual_fg == fg:
            _send_copy()
        elif not fg:
            _send_copy()
        else:
            # retry focus once more, then try anyway
            _set_foreground(fg)
            time.sleep(0.1)
            if _get_foreground() == fg:
                _send_copy()
            else:
                time.sleep(0.15)
                _wait_modifiers_up(0.25)
                continue

        wait = 2.0 if attempt == 0 else 1.5
        deadline = time.time() + wait
        while time.time() < deadline:
            time.sleep(0.05)
            seq = _clipboard_seq()
            if seq == seq0:
                continue
            time.sleep(0.1)
            value = _read_clipboard()
            if value.strip():
                # Ignore leftover sentinel-looking junk from older builds
                if value.startswith("__AI_PR_CAPTURE_"):
                    seq0 = seq
                    continue
                captured = value
                break
            seq0 = seq
        if captured:
            break
        seq0 = _clipboard_seq()
        if fg and not _is_our_window(fg):
            _set_foreground(fg)
        _wait_modifiers_up(0.3)

    log.info(
        "capture: len=%d attempts=%d focused=%s fg=%s",
        len(captured),
        attempts,
        focused,
        bool(fg),
    )
    return captured, original_clip, fg


def replace_text(corrected, original_clip, fg):
    _set_foreground(fg)
    time.sleep(0.12)
    pyperclip.copy(corrected)
    time.sleep(0.1)
    keyboard.send("ctrl+v")
    time.sleep(0.35)
    if original_clip is not None:
        pyperclip.copy(original_clip)


def copy_text(corrected):
    pyperclip.copy(corrected)


def _close_loading():
    global _loading
    if _loading is not None:
        try:
            _loading.close()
        except Exception:
            pass
        _loading = None


def _show_loading():
    global _loading
    from ui import LoadingPopup

    _close_loading()
    _loading = LoadingPopup(_root)


def _show_popup(original, corrected, original_clip, fg, provider=""):
    from ui import Popup

    Popup(
        _root,
        original,
        corrected,
        on_replace=lambda: replace_text(corrected, original_clip, fg),
        on_copy=lambda: copy_text(corrected),
        provider=provider,
    )


def _show_error(message):
    from ui import show_error

    _close_loading()
    show_error(_root, message)


def _background_update_check():
    import updater

    if not updater.update_repo():
        log.info("auto-update skipped: no update_repo configured")
        return

    def on_result(info):
        def apply():
            if info is None:
                log.info("auto-update: up to date")
                return
            if isinstance(info, Exception):
                log.info("auto-update check failed: %s", info)
                return
            log.info("auto-update available: %s", info.get("version"))
            from ui import show_update_dialog

            show_update_dialog(_root, info)

        ui(apply)

    updater.check_async(on_result)


def proofread_worker(text, original_clip, fg):
    result = {"text": "", "error": "", "provider": ""}
    try:
        result["text"] = check_text(text)
        result["provider"] = llm.LAST_PROVIDER
    except Exception as exc:
        log.error("proofread failed: %s", exc)
        result["error"] = str(exc)

    def done():
        _close_loading()
        if result["error"]:
            _show_error(result["error"])
            return
        history_store.add(text, result["text"], result["provider"])
        if get("auto_replace"):
            replace_text(result["text"], original_clip, fg)
        else:
            _show_popup(text, result["text"], original_clip, fg, result["provider"])
        _refresh_home()

    ui(done)


def _refresh_home():
    try:
        if _root is not None and hasattr(_root, "home"):
            _root.home.refresh()
    except Exception:
        pass


def on_hotkey():
    global _busy
    if not ENABLED or _busy:
        return
    if not available_providers():
        ui(
            _show_error,
            "No API keys configured (bring your own key). Open Settings → Providers "
            "and add at least one key.",
        )
        return
    # Capture source window BEFORE any of our UI is created
    pre_fg = _get_foreground()
    if _is_our_window(pre_fg):
        pre_fg = None
    log.info("hotkey: pre_fg=%s our=%s", pre_fg, _is_our_window(pre_fg))
    _busy = True
    # Loading must never activate (see LoadingPopup WS_EX_NOACTIVATE)
    ui(_show_loading)

    def run():
        global _busy
        try:
            # Small delay so loading window is mapped without stealing focus
            time.sleep(0.05)
            text, original_clip, fg = capture_selected_text(pre_fg)
            if not text.strip():
                log.info("no text captured (fg=%s)", bool(fg))
                ui(
                    _show_error,
                    "No text captured. Keep the text selected and make sure "
                    "the app window (Word/Notepad) is focused, then press the hotkey again.",
                )
                return
            log.info("captured %d chars", len(text))
            proofread_worker(text, original_clip, fg)
        except Exception as exc:
            log.exception("hotkey handler failed")
            ui(_show_error, str(exc))
        finally:
            _busy = False

    threading.Thread(target=run, daemon=True).start()


def rebind_hotkey():
    global _hotkey_hook
    hotkey = get("hotkey")
    try:
        if _hotkey_hook is not None:
            keyboard.remove_hotkey(_hotkey_hook)
    except Exception:
        pass
    _hotkey_hook = keyboard.add_hotkey(hotkey, on_hotkey)
    log.info("hotkey bound: %s", hotkey)


def set_enabled(enabled: bool):
    global ENABLED
    ENABLED = bool(enabled)
    settings = load_settings()
    settings["enabled"] = ENABLED
    config.save_settings(settings)
    log.info("enabled=%s", ENABLED)


def hide_to_tray():
    if _root is not None:
        _root.withdraw()
        log.info("hidden to tray")


def show_main():
    if _root is None:
        return
    _root.deiconify()
    _root.lift()
    _root.focus_force()
    try:
        _root.show_page("home")
    except Exception:
        pass


def on_settings_saved():
    rebind_hotkey()
    set_enabled(bool(get("enabled", True)))


def _tray_open(icon, item):
    ui(show_main)


def _tray_enabled(icon, item):
    set_enabled(not ENABLED)
    _refresh_home()


def _quit(icon, item):
    log.info("quit requested")
    if _icon is not None:
        _icon.stop()
    try:
        ui(_root.destroy)
    except Exception:
        pass


def _tray_icon_image():
    try:
        from config import app_dir

        icon_path = app_dir() / "assets" / "icon.ico"
        if icon_path.is_file():
            return Image.open(icon_path)
    except Exception:
        pass
    image = Image.new("RGB", (64, 64), (25, 55, 155))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((8, 8, 56, 56), radius=12, outline=(255, 255, 255), width=4)
    draw.line((18, 34, 46, 34), fill=(255, 255, 255), width=5)
    draw.ellipse((40, 16, 50, 26), fill=(120, 220, 120))
    return image


def start_tray():
    global _icon
    menu = pystray.Menu(
        pystray.MenuItem(
            "Enabled",
            _tray_enabled,
            checked=lambda item: ENABLED,
        ),
        pystray.MenuItem("Open AI Proofreader", _tray_open, default=True),
        pystray.MenuItem(f"v{VERSION}", None, enabled=False),
        pystray.MenuItem("Quit", _quit),
    )
    _icon = pystray.Icon("AI Proofreader", _tray_icon_image(), menu=menu)
    threading.Thread(target=_icon.run, daemon=True).start()


def main():
    global _root, ENABLED

    if not acquire_single_instance():
        if sys.platform == "win32":
            ctypes.windll.user32.MessageBoxW(
                None,
                "AI Proofreader is already running.",
                "AI Proofreader",
                0x40,
            )
        return

    setup_logging()
    settings = load_settings()
    ENABLED = bool(settings.get("enabled", True))

    from ui import MainWindow, apply_theme

    apply_theme()

    callbacks = {
        "set_enabled": set_enabled,
        "on_settings_saved": on_settings_saved,
        "hide_to_tray": hide_to_tray,
        "quit": lambda: _quit(None, None),
    }
    _root = MainWindow(callbacks)

    rebind_hotkey()
    start_tray()
    _root.after(50, _pump_ui)
    log.info("AI Proofreader v%s running (hotkey=%s)", VERSION, get("hotkey"))

    if settings.get("auto_update", True):
        _root.after(4000, _background_update_check)

    try:
        _root.mainloop()
    finally:
        try:
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass
        if _icon is not None:
            try:
                _icon.stop()
            except Exception:
                pass


if __name__ == "__main__":
    main()
