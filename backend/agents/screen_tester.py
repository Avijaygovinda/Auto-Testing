"""
Pass B — Screen Tester.

For each screen file, build a focused prompt:
    docs + app map + screen full source + dependency files (depth 1)
and ask Gemini for a deep, screen-specific test plan.

The dependency set comes from two sources, unioned:
    - the app map's `depends_on` for that screen (LLM-derived, semantic)
    - this file's own `import` statements that point at local project files
"""
import json
import os
import re
import time
from pathlib import Path
from typing import List, Dict, Optional

from google import genai
from google.genai import types
from dotenv import load_dotenv

from .codebase_scanner import DartFile
from ..utils.token_budget import (
    estimate_tokens,
    truncate_text,
    DEFAULT_MAX_INPUT_TOKENS,
)
from ..utils.logger import log_api_call
from ..utils.gemini_retry import call_with_retry

# Per-call hard cap. Leave room for response + safety margin.
PER_CALL_TOKEN_CAP = 180_000

# If a single dep file is bigger than this on its own, summarize via signatures
# instead of inlining full source.
DEP_INLINE_MAX_TOKENS = 6_000

# Match relative imports inside a Dart file: import '../models/product.dart';
RE_RELATIVE_IMPORT = re.compile(r"""import\s+['"]((?:\.{1,2}/|[^:'"]+\.dart)[^'"]*)['"]""")


def _load_prompt() -> str:
    return (Path(__file__).parent.parent / "prompts" / "screen_tester.txt").read_text(encoding="utf-8")


def _resolve_relative_imports(screen: DartFile, all_files: Dict[str, DartFile]) -> List[str]:
    """Return rel_paths for every local file directly imported by this screen.

    all_files is a dict keyed by rel_path (POSIX style) for quick lookup.
    """
    base = Path(screen.rel_path).parent
    found: List[str] = []
    for match in RE_RELATIVE_IMPORT.finditer(screen.content):
        spec = match.group(1)
        if spec.startswith("package:") or spec.startswith("dart:"):
            continue
        # Resolve relative path against this file's directory.
        try:
            target = (base / spec).as_posix()
            target = str(Path(target))
            # Normalize "lib/screens/../services/x.dart" → "lib/services/x.dart"
            target_norm = str(Path(target)).replace("\\", "/")
            target_norm = str(Path(target_norm).resolve()).replace("\\", "/") if False else _normpath(target_norm)
        except Exception:
            continue
        if target_norm in all_files:
            found.append(target_norm)
    return found


def _normpath(p: str) -> str:
    """Normalize a posix-ish path, collapsing '..' segments."""
    parts: list[str] = []
    for seg in p.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if parts:
                parts.pop()
            continue
        parts.append(seg)
    return "/".join(parts)


def _collect_deps(
    screen: DartFile,
    all_files: Dict[str, DartFile],
    app_map_deps: Optional[List[str]] = None,
) -> List[DartFile]:
    """Union of import-derived deps and app-map-derived deps. Stable order."""
    seen: set[str] = set()
    deps: List[DartFile] = []

    candidates = list(_resolve_relative_imports(screen, all_files))
    if app_map_deps:
        candidates.extend(app_map_deps)

    for rel in candidates:
        rel_norm = rel.replace("\\", "/")
        if rel_norm == screen.rel_path or rel_norm in seen:
            continue
        if rel_norm not in all_files:
            continue
        seen.add(rel_norm)
        deps.append(all_files[rel_norm])
    return deps


def _render_dep_block(dep: DartFile) -> str:
    """Inline full source if small, otherwise fall back to signatures only."""
    from .app_mapper import _extract_signatures  # local import to avoid cycle at module load
    body = dep.content
    if estimate_tokens(body) > DEP_INLINE_MAX_TOKENS:
        body = "(full source omitted to save tokens — signatures only)\n" + _extract_signatures(body, max_lines=80)
    return f"### Dependency: {dep.rel_path} (tags: {', '.join(dep.tags) or 'other'})\n```dart\n{body}\n```\n"


def build_screen_prompt(
    documentation: str,
    app_map: dict,
    screen: DartFile,
    deps: List[DartFile],
) -> str:
    template = _load_prompt()
    deps_block = "\n".join(_render_dep_block(d) for d in deps) or "(no local dependencies)"
    app_map_json = json.dumps(app_map, ensure_ascii=False, indent=2)

    return (
        f"{template}\n\n"
        f"===== PROJECT DOCUMENTATION =====\n{documentation}\n\n"
        f"===== APP MAP =====\n{app_map_json}\n\n"
        f"===== TARGET SCREEN: {screen.rel_path} =====\n"
        f"```dart\n{screen.content}\n```\n\n"
        f"===== DEPENDENCY FILES =====\n{deps_block}\n\n"
        f"Now return the JSON test plan for this screen:\n"
    )


def test_screen(
    screen: DartFile,
    all_files: Dict[str, DartFile],
    app_map: dict,
    documentation: str,
    *,
    sleep_before: float = 4.0,
) -> dict:
    """Run Pass B for one screen. Returns parsed test plan dict."""
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not found in env.")

    # Pull semantic deps the app map flagged for this screen.
    map_deps: List[str] = []
    for s in app_map.get("screens", []):
        if s.get("file") == screen.rel_path:
            map_deps = s.get("depends_on", []) or []
            break

    deps = _collect_deps(screen, all_files, map_deps)
    prompt = build_screen_prompt(documentation, app_map, screen, deps)

    tok = estimate_tokens(prompt)
    if tok > PER_CALL_TOKEN_CAP:
        # Last-resort guard: hard-truncate. Should rarely fire on real apps.
        prompt = truncate_text(prompt, PER_CALL_TOKEN_CAP)
        print(f"[screen_tester] WARNING: prompt exceeded {PER_CALL_TOKEN_CAP} tokens, truncated.")
        tok = estimate_tokens(prompt)
    print(f"[screen_tester] {screen.rel_path}: {len(deps)} deps, ~{tok} tokens.")

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
        label=f"screen_tester:{screen.rel_path}",
    )
    text = response.text

    log_api_call(
        model="gemini-2.5-flash",
        prompt=prompt,
        response=text,
        metadata={"pass": "B_screen", "screen": screen.rel_path, "dep_count": len(deps)},
    )
    return json.loads(text)


if __name__ == "__main__":
    # Smoke test: run Pass B for every screen, save per-screen JSON.
    import sys
    from .codebase_scanner import scan_flutter_project
    from .file_classifier import classify_all

    project = sys.argv[1] if len(sys.argv) > 1 else "../sample-flutter-app"
    doc_path = sys.argv[2] if len(sys.argv) > 2 else "../docs/sample-doc.md"
    map_path = sys.argv[3] if len(sys.argv) > 3 else "logs/app_map.json"

    files = classify_all(scan_flutter_project(project))
    by_path = {f.rel_path: f for f in files}
    documentation = Path(doc_path).read_text(encoding="utf-8")
    app_map = json.loads(Path(map_path).read_text(encoding="utf-8"))

    out_dir = Path(__file__).parent.parent / "logs" / "test_plan"
    out_dir.mkdir(parents=True, exist_ok=True)

    screens = [f for f in files if "screen" in f.tags]
    print(f"Running Pass B on {len(screens)} screens...")
    for sc in screens:
        plan = test_screen(sc, by_path, app_map, documentation)
        slug = Path(sc.rel_path).stem
        (out_dir / f"{slug}.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False))
        print(f"  saved {slug}.json — {len(plan.get('test_cases', []))} cases")
