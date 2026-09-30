import difflib
import re

_TOKEN_RE = re.compile(r"\S+\s*")


def _tokenize(text: str) -> list:
    return _TOKEN_RE.findall(text)


def diff_spans(original: str, corrected: str) -> list:
    """Segment `corrected` into (text, changed) spans.

    changed=True marks words that were inserted or replaced relative to
    `original`. Joining the texts of all spans reproduces `corrected` exactly.
    """
    a = _tokenize(original or "")
    b = _tokenize(corrected or "")
    spans = []
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for op, _i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            spans.append(("".join(b[j1:j2]), False))
        elif op in ("replace", "insert"):
            segment = "".join(b[j1:j2])
            if segment:
                spans.append((segment, True))
        # "delete" contributes nothing to the corrected text
    return spans


def preview_spans(spans: list, limit: int) -> list:
    """Truncate spans to at most `limit` characters of corrected text."""
    out = []
    used = 0
    for text, changed in spans:
        if used >= limit:
            break
        room = limit - used
        if len(text) > room:
            text = text[:room]
            out.append((text, changed))
            used = limit
            break
        out.append((text, changed))
        used += len(text)
    return out


def has_changes(spans: list) -> bool:
    return any(changed for _text, changed in spans)
