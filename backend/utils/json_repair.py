"""
Tolerant JSON parser for Gemini output.

Gemini's JSON-mode response is *usually* valid, but occasionally emits a
lone backslash inside a string (e.g. when echoing Dart source containing
`\$variable` or escape sequences it didn't re-escape). Strict json.loads
rejects those.

We try the strict parse first, then attempt a single repair pass that
double-escapes any backslash that isn't part of a valid JSON escape.
"""
import json
import re


_VALID_ESCAPE_AFTER = re.compile(r'\\(?!["\\/bfnrtu])')


def loads(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        repaired = _VALID_ESCAPE_AFTER.sub(r"\\\\", text)
        return json.loads(repaired)
