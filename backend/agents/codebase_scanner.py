"""
Codebase scanner — walks a Flutter project's lib/ folder and returns
every relevant .dart file with its content and basic metadata.

No AI here. Pure filesystem work.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

# Folders we never want to scan.
SKIP_DIRS = {"build", ".dart_tool", ".idea", ".vscode", "test", "ios", "android",
             "macos", "windows", "linux", "web"}

# Filename patterns that are auto-generated and would just bloat context.
SKIP_SUFFIXES = (".g.dart", ".freezed.dart", ".gr.dart", ".config.dart",
                 ".mocks.dart", ".pb.dart")


@dataclass
class DartFile:
    path: Path                 # absolute path on disk
    rel_path: str              # path relative to project root (for prompts)
    content: str               # full source
    line_count: int = 0
    size_bytes: int = 0
    tags: List[str] = field(default_factory=list)  # filled by classifier later

    def __post_init__(self):
        self.line_count = self.content.count("\n") + 1
        self.size_bytes = len(self.content.encode("utf-8"))


def scan_flutter_project(project_root: str | Path) -> List[DartFile]:
    """Walk project_root recursively and return all relevant .dart files.

    project_root should be the Flutter app folder (the one containing pubspec.yaml
    or lib/). We focus on lib/ since that's where app code lives.
    """
    root = Path(project_root).resolve()
    lib_dir = root / "lib"
    if not lib_dir.is_dir():
        raise FileNotFoundError(f"No lib/ folder under {root}")

    results: List[DartFile] = []
    for path in lib_dir.rglob("*.dart"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.name.endswith(SKIP_SUFFIXES):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        results.append(
            DartFile(
                path=path,
                rel_path=str(path.relative_to(root)),
                content=content,
            )
        )

    results.sort(key=lambda f: f.rel_path)
    return results


if __name__ == "__main__":
    # Quick smoke test against the sample app.
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "../sample-flutter-app"
    files = scan_flutter_project(target)
    print(f"Found {len(files)} dart files in {target}:")
    for f in files:
        print(f"  {f.rel_path}  ({f.line_count} lines, {f.size_bytes} bytes)")
