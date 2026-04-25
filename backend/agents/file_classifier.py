"""
File classifier — tags each Dart file with its likely role in the app.

Heuristic regex-based, NO AI. Tags drive how each file is treated downstream
(e.g. screens get the deep per-screen test-case pass; models/services get
summarized into context).

Tag vocabulary:
    entry      main.dart / app root
    route      route table / router config
    screen     full page (StatefulWidget/StatelessWidget that fills the screen)
    widget     reusable UI component, not a full screen
    model      plain data class (DTO, entity)
    service    network / persistence / business logic, no UI
    state      ChangeNotifier / Bloc / Cubit / Provider notifier
    util       helpers / constants / extensions
    other      fallback
"""
import re
from typing import List

from .codebase_scanner import DartFile

# --- Regex patterns. Keep these cheap and readable. ---
RE_WIDGET_CLASS   = re.compile(r"\bextends\s+(StatelessWidget|StatefulWidget|ConsumerWidget|HookWidget)\b")
RE_STATE_CLASS    = re.compile(r"\bextends\s+(ChangeNotifier|Bloc|Cubit|StateNotifier)\b")
RE_HAS_SCAFFOLD   = re.compile(r"\bScaffold\s*\(")
RE_HAS_HTTP       = re.compile(r"""(?x)
    \b(http\.|Dio\(|dio\.|HttpClient\(|fetch[A-Z]\w*\s*\()
""")
RE_FROM_JSON      = re.compile(r"\bfromJson\b")
RE_RUN_APP        = re.compile(r"\brunApp\s*\(")
RE_ROUTES_MAP     = re.compile(r"\b(routes|onGenerateRoute|GoRouter|MaterialApp|CupertinoApp)\b")
RE_FILENAME_SCREEN = re.compile(r"(?:^|[_/])(?:screen|page|view)s?\.dart$|(?:_screen|_page|_view)\.dart$", re.IGNORECASE)
RE_FILENAME_MODEL  = re.compile(r"/models?/", re.IGNORECASE)
RE_FILENAME_SERVICE = re.compile(r"/(services?|repositor(?:y|ies)|api)/", re.IGNORECASE)
RE_FILENAME_UTIL   = re.compile(r"/(utils?|helpers?|constants?|extensions?)/", re.IGNORECASE)


def classify(file: DartFile) -> List[str]:
    """Return a list of tags for the given file. Order: most specific first."""
    tags: List[str] = []
    src = file.content
    rel = file.rel_path.replace("\\", "/")

    # Entry point: main.dart with runApp().
    if file.path.name == "main.dart" and RE_RUN_APP.search(src):
        tags.append("entry")

    # Route table / router config (often inside main or a dedicated file).
    if RE_ROUTES_MAP.search(src) and ("routes:" in src or "GoRouter" in src or "onGenerateRoute" in src):
        tags.append("route")

    # State management classes.
    if RE_STATE_CLASS.search(src):
        tags.append("state")

    # Widget vs screen split.
    if RE_WIDGET_CLASS.search(src):
        is_screen_by_name = bool(RE_FILENAME_SCREEN.search(rel))
        is_screen_by_body = bool(RE_HAS_SCAFFOLD.search(src))
        if is_screen_by_name or is_screen_by_body:
            tags.append("screen")
        else:
            tags.append("widget")

    # Service / repository / API layer.
    if RE_FILENAME_SERVICE.search(rel) or RE_HAS_HTTP.search(src):
        if "screen" not in tags and "widget" not in tags:
            tags.append("service")

    # Plain data model.
    if RE_FILENAME_MODEL.search(rel) or (RE_FROM_JSON.search(src) and "screen" not in tags and "widget" not in tags):
        tags.append("model")

    # Utilities / helpers.
    if RE_FILENAME_UTIL.search(rel) and not tags:
        tags.append("util")

    if not tags:
        tags.append("other")

    return tags


def classify_all(files: List[DartFile]) -> List[DartFile]:
    """Tag every file in place and return the same list for chaining."""
    for f in files:
        f.tags = classify(f)
    return files


def group_by_tag(files: List[DartFile]) -> dict[str, List[DartFile]]:
    """Bucket files by their primary (first) tag — useful for downstream passes."""
    buckets: dict[str, List[DartFile]] = {}
    for f in files:
        primary = f.tags[0] if f.tags else "other"
        buckets.setdefault(primary, []).append(f)
    return buckets


if __name__ == "__main__":
    # Quick smoke test against the sample app.
    import sys
    from .codebase_scanner import scan_flutter_project

    target = sys.argv[1] if len(sys.argv) > 1 else "../sample-flutter-app"
    files = classify_all(scan_flutter_project(target))
    for f in files:
        print(f"  [{', '.join(f.tags):<20}]  {f.rel_path}")
