"""
Pass C — Flow Tester.

Generates cross-screen, end-to-end test cases that catch bugs single-screen
tests miss: state sync, persistence across navigation, stale data on back, etc.

Input: app map (with key_flows + navigation) plus a SUMMARY of each screen's
plan (not the full plan — keeps tokens small and avoids duplicating per-screen
tests). One Gemini call regardless of flow count.
"""
import json
import os
import time
from pathlib import Path
from typing import List

from google import genai
from google.genai import types
from dotenv import load_dotenv

from ..utils.token_budget import estimate_tokens, DEFAULT_MAX_INPUT_TOKENS
from ..utils.logger import log_api_call
from ..utils.gemini_retry import call_with_retry


def _summarize_screen_plan(plan: dict) -> dict:
    """Pull the bits useful for cross-screen reasoning. Drops full test cases."""
    cases = plan.get("test_cases", [])
    categories = sorted({tc.get("category", "OTHER") for tc in cases})
    return {
        "screen_name": plan.get("screen_name"),
        "screen_file": plan.get("screen_file"),
        "summary": plan.get("summary"),
        "test_categories_covered": categories,
        "test_case_count": len(cases),
        "open_questions": plan.get("questions_for_developer", []),
    }


def _load_prompt() -> str:
    return (Path(__file__).parent.parent / "prompts" / "flow_tester.txt").read_text(encoding="utf-8")


def build_flow_prompt(documentation: str, app_map: dict, screen_plans: List[dict]) -> str:
    template = _load_prompt()
    summaries = [_summarize_screen_plan(p) for p in screen_plans]

    return (
        f"{template}\n\n"
        f"===== PROJECT DOCUMENTATION =====\n{documentation}\n\n"
        f"===== APP MAP =====\n{json.dumps(app_map, indent=2, ensure_ascii=False)}\n\n"
        f"===== SCREEN SUMMARIES =====\n{json.dumps(summaries, indent=2, ensure_ascii=False)}\n\n"
        f"Now return the JSON flow test plan:\n"
    )


def test_flows(app_map: dict, screen_plans: List[dict], documentation: str,
               *, sleep_before: float = 4.0) -> dict:
    """Run Pass C. Returns dict with flow_test_cases + questions_for_developer."""
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not found in env.")

    prompt = build_flow_prompt(documentation, app_map, screen_plans)
    tok = estimate_tokens(prompt)
    print(f"[flow_tester] {len(screen_plans)} screens, "
          f"{len(app_map.get('key_flows', []))} flows, ~{tok} tokens.")
    if tok > DEFAULT_MAX_INPUT_TOKENS:
        raise RuntimeError(f"Flow prompt too big ({tok} tokens).")

    client = genai.Client(api_key=api_key)
    if sleep_before > 0:
        time.sleep(sleep_before)

    response = call_with_retry(
        lambda: client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.3,
            ),
        ),
        label="flow_tester",
    )
    text = response.text

    log_api_call(
        model="gemini-2.5-flash",
        prompt=prompt,
        response=text,
        metadata={"pass": "C_flows", "screen_count": len(screen_plans)},
    )
    return json.loads(text)
