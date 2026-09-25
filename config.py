import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

APP_NAME = "AI Proofreader"
APP_ID = "AIProofreader"
VERSION = "1.0.7"

DEFAULT_SETTINGS = {
    "hotkey": "ctrl+alt+z",
    "provider_order": ["groq", "gemini", "nvidia_nim", "deepseek"],
    "auto_replace": False,
    "enabled": True,
    "api_keys": {},
    "max_history": 100,
    "onboarded": False,
    "auto_update": True,
    "update_repo": "HITESHDAS-01/proofread_ai",
    "activated": False,
    "license_key": "",
    "tone": "professional",
    "translate_to": "",
    "ignore_words": [],
    "result_ui": "overlay",
    "smart_order": True,
    "wizard_done": False,
    "provider_stats": {},
}

PROVIDER_LABELS = {
    "groq": "Groq",
    "gemini": "Google Gemini",
    "nvidia_nim": "NVIDIA NIM",
    "deepseek": "DeepSeek",
    "openai": "OpenAI",
    "claude": "Anthropic Claude",
}

PROVIDER_ENV_KEYS = {
    "groq": "GROQ_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "nvidia_nim": "NVIDIA_NIM_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "openai": "OPENAI_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
}

PROVIDER_URLS = {
    "groq": "https://console.groq.com/keys",
    "gemini": "https://aistudio.google.com/app/apikey",
    "nvidia_nim": "https://build.nvidia.com/",
    "deepseek": "https://platform.deepseek.com/api_keys",
    "openai": "https://platform.openai.com/api-keys",
    "claude": "https://console.anthropic.com/settings/keys",
}

TONES = {
    "professional": (
        "Make the tone professional and polished."
    ),
    "formal": (
        "Rewrite in a formal register: complete sentences, no contractions, "
        "no slang or colloquialisms."
    ),
    "casual": (
        "Keep the text conversational and friendly — fix grammar and clarity "
        "without making it stiff or corporate."
    ),
    "short": (
        "Make the text concise: fix grammar and cut redundant words or "
        "phrases while keeping the original meaning."
    ),
    "academic": (
        "Use an academic style: precise, objective, and scholarly — "
        "no contractions, no informal expressions."
    ),
}

BASE_PROMPT = (
    "You are a proofreader. First detect the language of the input text. "
    "If the text mixes languages or uses romanized native words (e.g. Hinglish), "
    "keep the exact same language mix and script — do not convert it into a "
    "single language. "
    "Otherwise, correct grammar, spelling, and punctuation IN THE SAME LANGUAGE "
    "of the input — never translate, never switch scripts. "
    "If the text is English, also fix capitalization (sentence case). "
    "For other languages, follow that language's own capitalization and "
    "punctuation conventions. "
    "Preserve the original meaning, register, and formatting (line breaks, lists). "
)


def build_system_prompt(
    tone: str | None = None,
    translate_to: str | None = None,
    ignore_words: list | None = None,
) -> str:
    """Compose the system prompt from current settings.

    - tone: one of TONES keys (defaults to settings "tone", then "professional")
    - translate_to: target language name; empty/None keeps original language
    - ignore_words: words/names the model must not alter
    """
    if tone is None:
        tone = get("tone", "professional") or "professional"
    if translate_to is None:
        translate_to = get("translate_to", "") or ""
    if ignore_words is None:
        ignore_words = get("ignore_words", []) or []

    parts = [BASE_PROMPT]
    parts.append(TONES.get(tone, TONES["professional"]) + " ")
    target = str(translate_to).strip()
    if target:
        parts.append(
            f"After proofreading, translate the result into {target}. "
            "Return ONLY the translated text. "
        )
    else:
        parts.append(
            "Return the corrected text in the SAME language as the input. "
        )
    words = [str(w).strip() for w in ignore_words if str(w).strip()]
    if words:
        parts.append(
            "Do NOT change these words/names (leave them exactly as written): "
            + ", ".join(words)
            + ". "
        )
    parts.append("Return ONLY the text, no explanation.")
    return "".join(parts)


SYSTEM_PROMPT = build_system_prompt(
    tone="professional", translate_to="", ignore_words=[]
)

REQUEST_TIMEOUT = 30
MAX_RETRIES = 2


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def data_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    d = Path(base) / APP_ID
    d.mkdir(parents=True, exist_ok=True)
    return d


def log_file() -> Path:
    return data_dir() / "proofreader.log"


def settings_file() -> Path:
    return data_dir() / "settings.json"


def history_file() -> Path:
    return data_dir() / "history.json"


def env_file() -> Path:
    return app_dir() / ".env"


def _load_env() -> None:
    candidates = [
        app_dir() / ".env",
        Path.cwd() / ".env",
        Path(__file__).resolve().parent / ".env",
    ]
    for path in candidates:
        if path.is_file():
            load_dotenv(path)
            return
    load_dotenv()


_load_env()

API_KEYS: dict = {}

_ENV_ORDER = [
    p.strip().lower()
    for p in os.getenv("PROVIDER_ORDER", "").split(",")
    if p.strip()
]

_settings_cache: dict | None = None


def _env_keys() -> dict:
    return {
        name: (os.getenv(env, "") or "").strip()
        for name, env in PROVIDER_ENV_KEYS.items()
    }


def load_settings() -> dict:
    global _settings_cache
    if _settings_cache is not None:
        return dict(_settings_cache)
    merged = dict(DEFAULT_SETTINGS)
    merged["api_keys"] = dict(DEFAULT_SETTINGS["api_keys"])
    if _ENV_ORDER:
        merged["provider_order"] = _ENV_ORDER
    path = settings_file()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for key in DEFAULT_SETTINGS:
                    if key in data:
                        merged[key] = data[key]
        except (json.JSONDecodeError, OSError):
            pass
    if not merged.get("provider_order"):
        merged["provider_order"] = list(DEFAULT_SETTINGS["provider_order"])
    if not isinstance(merged.get("api_keys"), dict):
        merged["api_keys"] = {}
    if not isinstance(merged.get("max_history"), int):
        merged["max_history"] = 100
    if merged.get("tone") not in TONES:
        merged["tone"] = "professional"
    if not isinstance(merged.get("translate_to"), str):
        merged["translate_to"] = ""
    if not isinstance(merged.get("ignore_words"), list):
        merged["ignore_words"] = []
    if merged.get("result_ui") not in ("overlay", "popup"):
        merged["result_ui"] = "overlay"
    if not isinstance(merged.get("smart_order"), bool):
        merged["smart_order"] = True
    if not isinstance(merged.get("provider_stats"), dict):
        merged["provider_stats"] = {}
    _settings_cache = merged
    return dict(merged)


def save_settings(settings: dict) -> None:
    global _settings_cache
    merged = dict(DEFAULT_SETTINGS)
    merged.update(settings)
    if not isinstance(merged.get("api_keys"), dict):
        merged["api_keys"] = {}
    path = settings_file()
    path.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    _settings_cache = merged
    reload_api_keys()


def get(key, default=None):
    return load_settings().get(key, default)


def reload_api_keys() -> None:
    keys = _env_keys()
    for name, value in (load_settings().get("api_keys") or {}).items():
        if value:
            keys[name] = str(value).strip()
    API_KEYS.clear()
    API_KEYS.update(keys)


def write_env_key(provider: str) -> bool:
    env_name = PROVIDER_ENV_KEYS.get(provider)
    if not env_name:
        return False
    path = env_file()
    lines = []
    if path.is_file():
        lines = path.read_text(encoding="utf-8").splitlines()
    value = API_KEYS.get(provider, "")
    prefix = env_name + "="
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith(prefix):
            lines[i] = f"{prefix}{value}"
            found = True
            break
    if not found:
        lines.append(f"{prefix}{value}")
    try:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return True
    except OSError:
        return False


reload_api_keys()
