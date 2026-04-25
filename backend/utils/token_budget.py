"""
Token budget helper.

Gemini bills + caps by tokens, but we don't want to ship a full tokenizer
dependency just for rough planning. ~4 chars per token is the standard
back-of-envelope for English/code; good enough to keep us off the rails.

Use estimate_tokens() to size things up before a call, and trim_to_budget()
to chop a payload down when it would otherwise blow the limit.
"""
from typing import List

# Gemini 2.0 Flash is advertised as 1M-token input. Leave plenty of headroom
# for the prompt template, the docs blob, and the response.
DEFAULT_MAX_INPUT_TOKENS = 200_000

# Conservative chars-per-token. Real ratio for code is closer to 3.3, but
# overestimating is the safe direction for a budget guard.
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Rough token count. Always rounds up."""
    if not text:
        return 0
    return (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN


def estimate_total(parts: List[str]) -> int:
    return sum(estimate_tokens(p) for p in parts)


def fits(text: str, budget_tokens: int = DEFAULT_MAX_INPUT_TOKENS) -> bool:
    return estimate_tokens(text) <= budget_tokens


def truncate_text(text: str, max_tokens: int, marker: str = "\n... [truncated] ...\n") -> str:
    """Hard-cut text to max_tokens. Used as last resort before a call."""
    if estimate_tokens(text) <= max_tokens:
        return text
    keep_chars = max_tokens * CHARS_PER_TOKEN - len(marker)
    if keep_chars <= 0:
        return marker
    head = keep_chars // 2
    tail = keep_chars - head
    return text[:head] + marker + text[-tail:]
