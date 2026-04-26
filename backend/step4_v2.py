"""
FlowTest AI — Phase 4 v2 driver
================================
Drives a real Flutter app on a real device with AI-driven navigation,
human-in-the-loop fallback, and per-screen Gemini Vision UI bug analysis.

Generalized for arbitrary Flutter projects — not hardcoded to any sample.

Pipeline:
  1. Load Phase 2 app map (run step2_multi_file.py first if missing).
  2. Load documentation: user-provided file, or synthesize from code.
  3. Run integration_test on connected device. Test calls Mac host over
     HTTP for every nav decision; AI picks next action from screenshot +
     docs + app map. Low-confidence or destructive actions trigger a
     terminal HITL prompt. Each reached screen is screenshotted.
  4. Skip blank PNGs locally before vision pass.
  5. Run Gemini Vision UI bug analysis on remaining PNGs.
  6. Output: visual_report.json + interaction_log via screenshots/_manifest.

Usage:
    python step4_v2.py <project_root> [<doc_file>]

If <doc_file> is omitted, defaults to <project_root>/README.md. If that
also doesn't exist, docs are auto-synthesized from app_map.

Flags:
    --skip-vision     Capture screenshots but skip the per-screen vision pass.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.agents.codebase_scanner import scan_flutter_project
from backend.agents.file_classifier import classify_all
from backend.agents.realdevice_v2.runner import run_on_device
from backend.agents.realdevice_v2.doc_synthesizer import synthesize_docs
from backend.agents.realdevice_v2.blank_filter import is_blank
from backend.agents.visual_tester import analyze_project_screenshots


def _load_or_synth_docs(project_root: Path, doc_path: Path | None,
                         app_map: dict) -> str:
    if doc_path and doc_path.is_file():
        return doc_path.read_text(encoding="utf-8")
    print("[docs] no usable docs provided — synthesizing from code…")
    files = classify_all(scan_flutter_project(project_root))
    screen_files = [f for f in files if "screen" in f.tags][:6]  # cap excerpts
    excerpts = {f.rel_path: f.content for f in screen_files}
    return synthesize_docs(app_map=app_map, screen_sources=excerpts)


def _filter_blank(screenshots_dir: Path) -> list[str]:
    """Return list of PNG paths that are NOT blank — feed only these to vision."""
    keep: list[str] = []
    for png in sorted(screenshots_dir.rglob("*.png")):
        blank, info = is_blank(png)
        if blank:
            print(f"[blank] {png.relative_to(screenshots_dir)}: skipped ({info['dominant_fraction']*100:.0f}% one color)")
            continue
        keep.append(str(png))
    return keep


def run(project_root: str, doc_path: str | None, *, skip_vision: bool = False) -> None:
    project = Path(project_root).resolve()
    backend_logs_dir = Path(__file__).parent / "logs"
    backend_logs_dir.mkdir(exist_ok=True)
    app_map_path = backend_logs_dir / "app_map.json"
    if not app_map_path.is_file():
        print("ERROR: app_map.json missing. Run step2_multi_file.py first.")
        sys.exit(1)
    app_map = json.loads(app_map_path.read_text())

    print(f"[1/4] Loading documentation…")
    doc = Path(doc_path) if doc_path else (project / "README.md")
    docs = _load_or_synth_docs(project, doc, app_map)
    (backend_logs_dir / "docs_used.md").write_text(docs)
    print(f"      {len(docs)} chars of docs ready (saved to backend/logs/docs_used.md).")

    print(f"[2/4] Running on connected device — AI navigation + HITL prompts active.")
    print(f"      You may see prompts in this terminal. Answer y/n or as instructed.")
    result = run_on_device(project, backend_logs_dir,
                           app_map=app_map, documentation=docs)
    print(f"      Captured {len(result['saved_pngs'])} PNGs at {result['screenshots_dir']}.")

    print(f"[3/4] Filtering blank PNGs (no Vision call needed for those)…")
    keep = _filter_blank(Path(result["screenshots_dir"]))
    print(f"      {len(keep)} non-blank PNGs will be analyzed.")

    visual_report = None
    if skip_vision:
        print("[4/4] Skipping vision pass (--skip-vision).")
    else:
        print(f"[4/4] Running Gemini Vision UI bug analysis…")
        plan_dir = backend_logs_dir / "test_plan"
        plans_by_name: dict[str, dict] = {}
        if plan_dir.is_dir():
            for jf in plan_dir.glob("*.json"):
                if jf.name.startswith("_"):
                    continue
                try:
                    data = json.loads(jf.read_text())
                except json.JSONDecodeError:
                    continue
                plans_by_name[data.get("screen_name", jf.stem)] = data
        report_path = backend_logs_dir / "visual_report.json"
        # Reuse Phase 3b's analyzer; it walks the screenshots dir tree.
        visual_report = analyze_project_screenshots(
            Path(result["screenshots_dir"]),
            app_map,
            plans_by_name,
            existing_report_path=report_path,
        )
        report_path.write_text(json.dumps(visual_report, indent=2, ensure_ascii=False))
        print(f"      {visual_report['total_issues_found']} UI issues, "
              f"severity {visual_report['severity_counts']}.")

    print()
    print("=" * 70)
    print(f"PNGs:           {len(result['saved_pngs'])} at {result['screenshots_dir']}")
    print(f"Manifest:       {result['screenshots_dir']}/_manifest.json")
    if visual_report is not None:
        print(f"Visual report:  backend/logs/visual_report.json "
              f"({visual_report['total_issues_found']} issues)")
    print("=" * 70)


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    skip_vision = "--skip-vision" in sys.argv
    if not args:
        print(__doc__)
        sys.exit(1)
    project = args[0]
    doc = args[1] if len(args) > 1 else None
    run(project, doc, skip_vision=skip_vision)


if __name__ == "__main__":
    main()
