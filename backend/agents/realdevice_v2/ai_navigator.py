"""
AI navigator — given the current screen state and a goal, ask Gemini Vision
what action to take next. Returns a structured action plus a confidence
level so the caller can decide whether to fall back to HITL.

Same module also provides verification (does the new screen match what we
expected?) and UI bug analysis (existing visual_tester reuse).
"""
import json
import os
from pathlib import Path
from typing import Optional

from google import genai
from google.genai import types
from dotenv import load_dotenv

from ...utils.gemini_retry import call_with_retry
from ...utils.logger import log_api_call


_NAV_PROMPT = """You are an autonomous QA agent driving a Flutter app on a real Android phone.

You will be given:
- The CURRENT SCREEN screenshot (as image).
- The CURRENT SCREEN NAME (a guess — verify against screenshot).
- The TARGET SCREEN NAME we want to reach next.
- The APP MAP (screens, navigation graph, key flows).
- DOCUMENTATION (developer-written or AI-synthesized) describing how the app works.
- Any TEST CREDENTIALS available (email, password, OTP, etc.).

Your job: decide the SINGLE NEXT ACTION the test should take to make progress
towards the target. Be specific, grounded in what is actually visible in the
screenshot, and consistent with the documentation.

Output ONLY a JSON object with this exact shape:

{
  "action": "tap_text" | "tap_icon" | "tap_widget_type" | "tap_first_of_type" | "enter_text" | "scroll_down" | "scroll_up" | "back" | "wait" | "hitl" | "skip",
  "selector": "string used by the action (text label, icon name, widget type)",
  "input_text": "ONLY for enter_text — what to type",
  "field_index": 0,
  "wait_after_seconds": 3,
  "confidence": "high" | "medium" | "low",
  "reasoning": "why this action — reference visible elements and docs",
  "is_destructive": false,
  "expected_screen_after": "name of screen we expect after the action"
}

Rules:
- If the screen is showing a login form and TARGET requires authentication,
  use enter_text actions to fill credentials, then tap_text 'Login' (or
  whatever the actual button label is). For enter_text, set "field_index"
  to the zero-based index of the TextField you want to type into (counting
  TextFields visible top-to-bottom, left-to-right). Do not re-fill a field
  that already has text — pick the next empty field.
- If the screen is a permission popup, return tap_native_dialog with
  selector = the button text ('Allow', 'While using app', etc.).
- If the action would PERMANENTLY DELETE data, place an order, send a
  message, etc., set is_destructive=true.
- If you're unsure between two plausible options OR confidence < high on a
  destructive action OR target is unreachable from current screen, set
  action='hitl' with reasoning describing what the user should clarify.
- Do not invent UI elements that aren't in the screenshot. Only refer to
  what you can see.
- Output strictly valid JSON, no markdown fences.
"""


_VERIFY_PROMPT = """You are an autonomous QA agent verifying a navigation result.

You attempted an action expecting to land on EXPECTED SCREEN.
You will be given the CURRENT SCREEN screenshot.

Output ONLY a JSON object:

{
  "matches_expected": true | false,
  "actual_screen_guess": "best guess at what screen this is",
  "confidence": "high" | "medium" | "low",
  "drift_detected": "string if docs and reality differ; otherwise empty"
}
"""


def _client() -> genai.Client:
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not found in env.")
    return genai.Client(api_key=api_key)


def decide_next_action(
    *,
    screenshot_bytes: bytes,
    current_screen_guess: str,
    target_screen: str,
    app_map: dict,
    documentation: str,
    test_creds: dict[str, str],
) -> dict:
    """Ask Gemini Vision what to do next. Returns action JSON dict."""
    client = _client()
    creds_visible = {k: ("***" if "PASSWORD" in k or "OTP" in k else v) for k, v in test_creds.items()}
    context = (
        f"{_NAV_PROMPT}\n\n"
        f"===== CURRENT SCREEN GUESS =====\n{current_screen_guess}\n\n"
        f"===== TARGET SCREEN =====\n{target_screen}\n\n"
        f"===== APP MAP =====\n{json.dumps(app_map, indent=2, ensure_ascii=False)}\n\n"
        f"===== DOCUMENTATION =====\n{documentation[:8000]}\n\n"
        f"===== TEST CREDENTIALS AVAILABLE =====\n{json.dumps(creds_visible, indent=2)}\n\n"
        f"Now return the JSON action:\n"
    )
    response = call_with_retry(
        lambda: client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(data=screenshot_bytes, mime_type="image/png"),
                context,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
            ),
        ),
        label=f"navigator:{target_screen}",
    )
    text = response.text
    log_api_call(
        model="gemini-2.5-flash",
        prompt=context,
        response=text,
        metadata={"phase": "4v2_nav", "target": target_screen},
    )
    from ...utils import json_repair
    parsed = json_repair.loads(text)
    # Inject the actual cred value when input_text references a placeholder.
    if parsed.get("action") == "enter_text":
        it = parsed.get("input_text", "")
        for k, v in test_creds.items():
            if k in it:
                parsed["input_text"] = it.replace(k, v)
    return parsed


def verify_screen(
    *,
    screenshot_bytes: bytes,
    expected_screen: str,
    documentation: str,
) -> dict:
    """Ask Gemini whether the current screen matches the expected target."""
    client = _client()
    context = (
        f"{_VERIFY_PROMPT}\n\n"
        f"===== EXPECTED SCREEN =====\n{expected_screen}\n\n"
        f"===== DOCUMENTATION =====\n{documentation[:6000]}\n\n"
    )
    response = call_with_retry(
        lambda: client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(data=screenshot_bytes, mime_type="image/png"),
                context,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        ),
        label=f"verifier:{expected_screen}",
    )
    text = response.text
    log_api_call(
        model="gemini-2.5-flash",
        prompt=context,
        response=text,
        metadata={"phase": "4v2_verify", "expected": expected_screen},
    )
    from ...utils import json_repair
    return json_repair.loads(text)
