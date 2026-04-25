"""
Pass A — App Mapper.

Builds a compact inventory of every Dart file (path + tags + signature snippet)
and asks Gemini to produce a high-level mental model of the app: screens,
models, services, navigation graph, key user flows, open questions.

Output is one JSON file used as context for the per-screen pass (Pass B).
"""
import json
import os
import re
import time
from pathlib import Path
from typing import List

from google import genai
from google.genai import types
from dotenv import load_dotenv

from .codebase_scanner import DartFile
from ..utils.token_budget import estimate_tokens, DEFAULT_MAX_INPUT_TOKENS
from ..utils.logger import log_api_call
from ..utils.gemini_retry import call_with_retry

# How many lines of "signature" we extract per file for the inventory.
SIGNATURE_MAX_LINES = 25

RE_SIGNATURE = re.compile(
    r"^\s*(?:"
    r"class\s+\w+|"            # class declarations
    r"abstract\s+class\s+\w+|"
    r"mixin\s+\w+|"
    r"enum\s+\w+|"
    r"typedef\s+\w+|"
    r"(?:Future<[^>]*>|void|String|int|bool|double|List<[^>]*>|Map<[^>]*>|\w+)\s+\w+\s*\("  # top-level fns / methods
    r")"
)


def _extract_signatures(content: str, max_lines: int = SIGNATURE_MAX_LINES) -> str:
    """Pull a compact view of a Dart file: class headers + method signatures.

    Avoids shipping every line of every file in the inventory — keeps tokens down
    while still letting the model see the *shape* of the code.
    """
    picked: list[str] = []
    for line in content.splitlines():
        if RE_SIGNATURE.match(line):
            picked.append(line.rstrip())
            if len(picked) >= max_lines:
                break
    if not picked:
        # Fall back to first few non-empty lines so the model isn't flying blind.
        for line in content.splitlines():
            if line.strip():
                picked.append(line.rstrip())
                if len(picked) >= 6:
                    break
    return "\n".join(picked)


def build_inventory(files: List[DartFile]) -> str:
    """Render the file list as a compact human/LLM-readable inventory block."""
    blocks = []
    for f in files:
        sig = _extract_signatures(f.content)
        tags = ", ".join(f.tags) if f.tags else "other"
        block = (
            f"### {f.rel_path}\n"
            f"tags: {tags}\n"
            f"lines: {f.line_count}\n"
            f"signatures:\n{sig}\n"
        )
        blocks.append(block)
    return "\n".join(blocks)


def _load_prompt() -> str:
    return (Path(__file__).parent.parent / "prompts" / "app_mapper.txt").read_text(encoding="utf-8")


def build_full_prompt(documentation: str, inventory: str) -> str:
    template = _load_prompt()
    return (
        f"{template}\n\n"
        f"===== PROJECT DOCUMENTATION =====\n{documentation}\n\n"
        f"===== FILE INVENTORY =====\n{inventory}\n\n"
        f"Now return the JSON app map:\n"
    )


def map_app(files: List[DartFile], documentation: str, *, sleep_before: float = 4.0) -> dict:
    """Run Pass A: send inventory + docs to Gemini, return parsed app map dict."""
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not found in env.")

    inventory = build_inventory(files)
    full_prompt = build_full_prompt(documentation, inventory)

    tok = estimate_tokens(full_prompt)
    print(f"[app_mapper] inventory covers {len(files)} files, ~{tok} tokens.")
    if tok > DEFAULT_MAX_INPUT_TOKENS:
        raise RuntimeError(
            f"Inventory too big ({tok} tokens > {DEFAULT_MAX_INPUT_TOKENS}). "
            f"Trim signatures or split the project."
        )

    client = genai.Client(api_key=api_key)
    if sleep_before > 0:
        time.sleep(sleep_before)  # avoid free-tier rate limit when chained

    print("[app_mapper] calling Gemini Flash...")
    response = call_with_retry(
        lambda: client.models.generate_content(
            model="gemini-2.5-flash",
            contents=full_prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
            ),
        ),
        label="app_mapper",
    )
    text = response.text

    log_api_call(
        model="gemini-2.5-flash",
        prompt=full_prompt,
        response=text,
        metadata={"pass": "A_app_map", "file_count": len(files)},
    )
    return json.loads(text)


if __name__ == "__main__":
    # Quick end-to-end smoke test.
    import sys
    from .codebase_scanner import scan_flutter_project
    from .file_classifier import classify_all

    project = sys.argv[1] if len(sys.argv) > 1 else "../sample-flutter-app"
    doc_path = sys.argv[2] if len(sys.argv) > 2 else "../docs/sample-doc.md"

    files = classify_all(scan_flutter_project(project))
    documentation = Path(doc_path).read_text(encoding="utf-8")
    app_map = map_app(files, documentation)

    out = Path(__file__).parent.parent / "logs" / "app_map.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(app_map, indent=2, ensure_ascii=False))
    print(f"\nApp map saved to: {out}")
    print(f"Screens detected: {[s['name'] for s in app_map.get('screens', [])]}")
    print(f"Key flows: {[f['name'] for f in app_map.get('key_flows', [])]}")
