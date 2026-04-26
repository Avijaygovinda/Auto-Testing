"""
Human-in-the-loop prompt — pauses the run and asks the developer for input
when the AI is uncertain or about to do something destructive.
"""
import os
from typing import Optional

# ANSI bold for visibility in busy terminals.
_BOLD = "\x1b[1m"
_YELLOW = "\x1b[33m"
_CYAN = "\x1b[36m"
_RESET = "\x1b[0m"


def confirm(question: str, default: bool = False) -> bool:
    """Y/N prompt. Honors auto-yes / auto-no env flags for unattended runs."""
    auto = os.getenv("FLOWTEST_AUTO_CONFIRM", "").lower()
    if auto in ("y", "yes", "true", "1"):
        print(f"{_YELLOW}[HITL auto-yes]{_RESET} {question}")
        return True
    if auto in ("n", "no", "false", "0"):
        print(f"{_YELLOW}[HITL auto-no]{_RESET} {question}")
        return False

    suffix = "[Y/n]" if default else "[y/N]"
    answer = input(f"{_BOLD}{_CYAN}?? {question} {suffix}: {_RESET}").strip().lower()
    if not answer:
        return default
    return answer in ("y", "yes")


def ask_text(question: str, default: Optional[str] = None) -> str:
    suffix = f" (default: {default})" if default else ""
    answer = input(f"{_BOLD}{_CYAN}?? {question}{suffix}: {_RESET}").strip()
    if not answer and default is not None:
        return default
    return answer


def ask_choice(question: str, options: list[str]) -> str:
    print(f"{_BOLD}{_CYAN}?? {question}{_RESET}")
    for i, opt in enumerate(options, 1):
        print(f"   {i}) {opt}")
    while True:
        raw = input(f"{_CYAN}Choose 1-{len(options)}: {_RESET}").strip()
        try:
            idx = int(raw)
            if 1 <= idx <= len(options):
                return options[idx - 1]
        except ValueError:
            continue
        print(f"  Invalid. Pick 1-{len(options)}.")
