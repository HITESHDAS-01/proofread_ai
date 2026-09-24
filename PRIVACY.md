# Privacy Policy — AI Proofreader

**Last updated:** 2026-09-24

AI Proofreader ("the app") is a local desktop application. This policy
explains what data it handles.

## What the app does NOT do

- No analytics or telemetry
- No accounts or registration
- No advertising
- No cloud backend operated by the developer
- No selling or sharing of personal data

## Data stored locally (on your PC only)

| Data | Location | Purpose |
|------|----------|---------|
| Settings (hotkey, preferences) | `%APPDATA%\AIProofreader\settings.json` | Remember your choices |
| API keys you enter | `%APPDATA%\AIProofreader\settings.json` | Call the LLM you configured |
| Correction history | `%APPDATA%\AIProofreader\history.json` | Show past corrections |
| Log file | `%APPDATA%\AIProofreader\proofreader.log` | Debugging |

You can delete this folder at any time to erase local data.

## Data sent to third parties

When you press the hotkey, the **selected text** (and only that text) is
sent over HTTPS to the LLM API provider **you** configured (e.g. Groq,
Google Gemini, NVIDIA NIM, DeepSeek).

- Providers process data under **their** privacy policies.
- The developer does not receive, store, or view your text or API keys.
- Your API keys are used only to authenticate requests to the provider
  you chose.

## Clipboard

The app reads the clipboard to capture your selection and may restore it
after Replace. Clipboard content is not written to disk except as part of
correction history (local only).

## Children

The app is not directed at children under 13.

## Changes

Material changes will be reflected in this file with an updated date.

## Contact

Developer: Pranjit Das
