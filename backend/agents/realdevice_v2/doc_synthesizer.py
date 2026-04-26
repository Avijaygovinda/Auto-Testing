"""
Doc synthesizer — when the user provides no README/doc file, build a
synthetic one by asking Gemini to read the app map + a few representative
screen sources and describe what the app does in plain English.

Output is fed into nav decisions just like a real doc would be.
"""
import json
import os
from pathlib import Path

from google import genai
from google.genai import types
from dotenv import load_dotenv

from ...utils.gemini_retry import call_with_retry
from ...utils.logger import log_api_call


_PROMPT = """You will be given the APP MAP of a Flutter app (screens, models,
services, navigation, key flows) and SHORT EXCERPTS of the screen source code.

Your job: write a concise project README (markdown) that describes:
- What the app does in 2-3 sentences.
- Each screen's purpose, key UI elements, and how to navigate to it.
- Any user flows you can infer (login → home → checkout, etc.).
- Any cross-cutting behavior worth knowing (persistence, authentication, network).

This README will be used by an autonomous QA agent to navigate the app and
test each screen, so be specific about navigation triggers ("tap the bookmark
icon in the AppBar", "tap any movie poster in the grid") rather than generic
descriptions.

Output only the markdown, no JSON wrapper, no fences.
"""


def synthesize_docs(
    *,
    app_map: dict,
    screen_sources: dict[str, str],
    cap_chars_per_file: int = 1500,
) -> str:
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set.")

    excerpts = "\n\n".join(
        f"### {p}\n```dart\n{src[:cap_chars_per_file]}\n```"
        for p, src in screen_sources.items()
    )
    full_prompt = (
        f"{_PROMPT}\n\n"
        f"===== APP MAP =====\n{json.dumps(app_map, indent=2, ensure_ascii=False)}\n\n"
        f"===== SCREEN EXCERPTS =====\n{excerpts}\n"
    )
    client = genai.Client(api_key=api_key)
    response = call_with_retry(
        lambda: client.models.generate_content(
            model="gemini-2.5-flash",
            contents=full_prompt,
            config=types.GenerateContentConfig(temperature=0.3),
        ),
        label="doc_synthesizer",
    )
    text = response.text
    log_api_call(
        model="gemini-2.5-flash",
        prompt=full_prompt,
        response=text,
        metadata={"phase": "4v2_doc_synth"},
    )
    return text
