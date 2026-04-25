"""
FlowTest AI — Phase 1 Prototype
================================
The smallest possible script that proves the core idea works.

What it does:
    1. Reads project documentation (markdown file)
    2. Reads ONE Flutter screen file (.dart)
    3. Sends both to Gemini Flash with a structured prompt
    4. Outputs test cases as JSON

Usage:
    python step1_prototype.py <doc_file> <dart_file>

Example:
    python step1_prototype.py ../docs/sample-doc.md ../sample-flutter-app/lib/login_screen.dart
"""
import os
import sys
import json
import time
from pathlib import Path

from google import genai
from google.genai import types
from dotenv import load_dotenv

# Local imports
sys.path.insert(0, str(Path(__file__).parent))
from utils.logger import log_api_call


def load_prompt_template() -> str:
    """Load the test case generator prompt from the prompts folder."""
    prompt_path = Path(__file__).parent / "prompts" / "test_case_generator.txt"
    return prompt_path.read_text(encoding="utf-8")


def build_full_prompt(documentation: str, dart_code: str, dart_filename: str) -> str:
    """Combine the prompt template with the actual content."""
    template = load_prompt_template()
    return f"""{template}

===== PROJECT DOCUMENTATION =====
{documentation}

===== FLUTTER SCREEN CODE =====
File: {dart_filename}

```dart
{dart_code}
```

Now generate the test cases as JSON:
"""


def generate_test_cases(doc_path: str, dart_path: str) -> dict:
    """Main function — reads files, calls Gemini, returns parsed test cases."""
    # 1. Load environment
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY not found. Copy .env.example to .env and add your key."
        )

    # 2. Read input files
    doc_content = Path(doc_path).read_text(encoding="utf-8")
    dart_content = Path(dart_path).read_text(encoding="utf-8")
    dart_filename = Path(dart_path).name

    # 3. Build the prompt
    full_prompt = build_full_prompt(doc_content, dart_content, dart_filename)

    # 4. Configure Gemini and call
    client = genai.Client(api_key=api_key)

    # Throttle to stay under free-tier rate limit when called in a loop.
    time.sleep(4)

    print(f"Calling Gemini Flash for {dart_filename}...")
    response = client.models.generate_content(
        model="gemini-flash-latest",
        contents=full_prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.3,
        ),
    )
    response_text = response.text

    # 5. Log it (critical for prompt iteration)
    log_api_call(
        model="gemini-2.0-flash",
        prompt=full_prompt,
        response=response_text,
        metadata={"dart_file": dart_filename, "doc_file": Path(doc_path).name},
    )

    # 6. Parse and return
    return json.loads(response_text)


def print_test_cases(result: dict):
    """Print test cases in a readable format."""
    print("\n" + "=" * 70)
    print(f"SCREEN: {result.get('screen_name', 'Unknown')}")
    print(f"SUMMARY: {result.get('summary', '')}")
    print("=" * 70)

    test_cases = result.get("test_cases", [])
    print(f"\nGenerated {len(test_cases)} test cases:\n")

    for tc in test_cases:
        print(f"[{tc['id']}] [{tc['category']}] [{tc['priority']}] {tc['title']}")
        print(f"   Why: {tc['reasoning']}")
        print(f"   Steps:")
        for i, step in enumerate(tc["steps"], 1):
            print(f"      {i}. {step}")
        print(f"   Expected: {tc['expected_result']}")
        print()

    questions = result.get("questions_for_developer", [])
    if questions:
        print("\n" + "-" * 70)
        print("QUESTIONS FOR DEVELOPER (AI was unsure about these):")
        print("-" * 70)
        for q in questions:
            print(f"  ? {q}")


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    doc_path = sys.argv[1]
    dart_path = sys.argv[2]

    try:
        result = generate_test_cases(doc_path, dart_path)
        print_test_cases(result)

        # Save full output to file
        output_path = Path(__file__).parent / "logs" / "last_run_output.json"
        output_path.parent.mkdir(exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
        print(f"\nFull output saved to: {output_path}")

    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
