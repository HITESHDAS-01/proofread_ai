import logging
import time

import requests

from config import (
    API_KEYS,
    MAX_RETRIES,
    REQUEST_TIMEOUT,
    SYSTEM_PROMPT,
    get,
)

log = logging.getLogger(__name__)

LAST_PROVIDER = ""


class ProviderError(Exception):
    pass


def _post_json(url, headers, payload):
    last_exc = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.post(
                url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT
            )
            if resp.status_code == 429 or resp.status_code >= 500:
                last_exc = ProviderError(
                    f"HTTP {resp.status_code}: {resp.text[:200]}"
                )
                if attempt < MAX_RETRIES:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise last_exc
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < MAX_RETRIES:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
    raise last_exc or ProviderError("request failed")


def groq_complete(text, system_prompt):
    data = _post_json(
        "https://api.groq.com/openai/v1/chat/completions",
        {"Authorization": f"Bearer {API_KEYS['groq']}"},
        {
            "model": "openai/gpt-oss-120b",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
        },
    )
    return data["choices"][0]["message"]["content"].strip()


def gemini_complete(text, system_prompt):
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-1.5-flash:generateContent"
    )
    data = _post_json(
        url,
        {"x-goog-api-key": API_KEYS["gemini"]},
        {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"parts": [{"text": text}]}],
        },
    )
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()


def nvidia_nim_complete(text, system_prompt):
    data = _post_json(
        "https://integrate.api.nvidia.com/v1/chat/completions",
        {"Authorization": f"Bearer {API_KEYS['nvidia_nim']}"},
        {
            "model": "qwen/qwen3.8-27b",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
        },
    )
    return data["choices"][0]["message"]["content"].strip()


def deepseek_complete(text, system_prompt):
    data = _post_json(
        "https://api.deepseek.com/v1/chat/completions",
        {"Authorization": f"Bearer {API_KEYS['deepseek']}"},
        {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
        },
    )
    return data["choices"][0]["message"]["content"].strip()


def openai_complete(text, system_prompt):
    data = _post_json(
        "https://api.openai.com/v1/chat/completions",
        {"Authorization": f"Bearer {API_KEYS['openai']}"},
        {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
        },
    )
    return data["choices"][0]["message"]["content"].strip()


def claude_complete(text, system_prompt):
    data = _post_json(
        "https://api.anthropic.com/v1/messages",
        {
            "x-api-key": API_KEYS["claude"],
            "anthropic-version": "2023-06-01",
        },
        {
            "model": "claude-3-5-haiku-latest",
            "max_tokens": 4096,
            "system": system_prompt,
            "messages": [{"role": "user", "content": text}],
        },
    )
    return data["content"][0]["text"].strip()


PROVIDERS = {
    "groq": groq_complete,
    "gemini": gemini_complete,
    "nvidia_nim": nvidia_nim_complete,
    "deepseek": deepseek_complete,
    "openai": openai_complete,
    "claude": claude_complete,
}


def available_providers(order=None):
    if order is None:
        order = get("provider_order")
    return [name for name in order if name in PROVIDERS and API_KEYS.get(name)]


def test_provider(name: str) -> tuple:
    fn = PROVIDERS.get(name)
    if fn is None:
        return False, "unknown provider"
    if not API_KEYS.get(name):
        return False, "no API key"
    try:
        out = fn("this is a test sentance", SYSTEM_PROMPT)
        if not out:
            return False, "empty response"
        return True, out.strip()[:80]
    except Exception as exc:
        return False, str(exc)


def check_text(text, system_prompt=SYSTEM_PROMPT):
    global LAST_PROVIDER
    order = get("provider_order")
    errors = []
    tried = False
    for name in order:
        fn = PROVIDERS.get(name)
        if fn is None:
            errors.append(f"{name}: unknown provider")
            continue
        if not API_KEYS.get(name):
            errors.append(f"{name}: missing API key")
            continue
        tried = True
        log.info("trying provider: %s", name)
        try:
            result = fn(text, system_prompt)
            if not result:
                raise ProviderError("empty response")
            LAST_PROVIDER = name
            log.info("provider %s succeeded", name)
            return result
        except Exception as exc:
            log.warning("provider %s failed: %s", name, exc)
            errors.append(f"{name}: {exc}")
    if not tried:
        raise ProviderError(
            "No API keys configured (bring your own key). "
            "Open Settings → Providers and add a key."
        )
    raise ProviderError("All providers failed -> " + " | ".join(errors))
