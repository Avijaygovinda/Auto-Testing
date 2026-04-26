"""
FlowTest AI — Phase 3 Driver (3a — screenshot capture only)
===========================================================
Generates a temporary Dart test harness in the target Flutter project, runs
`flutter test`, and harvests multi-resolution PNGs of every supported screen.

No emulator. No AVD. No external Flutter packages added to the target project —
the harness uses only what ships with the Flutter SDK.

Phase 3b (Gemini Vision analysis) will consume the produced PNGs in a later
step and is NOT run here.

Usage:
    python step3_visual.py <project_root> [<app_map.json>]

Example:
    python step3_visual.py ../sample-flutter-app

Output:
    backend/logs/screenshots/<project>/<screen>/<WxH>.png
    backend/logs/screenshots/<project>/_manifest.json
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.agents.screenshot_codegen import generate_harness
from backend.agents.screenshot_runner import run_harness
from backend.agents.visual_tester import analyze_project_screenshots


def run(project_root: str, app_map_path: str, *, cleanup: bool = True,
        skip_vision: bool = False) -> None:
    backend_logs_dir = Path(__file__).parent / "logs"
    backend_logs_dir.mkdir(exist_ok=True)

    print(f"[1/4] Generating screenshot harness for {project_root}...")
    codegen = generate_harness(project_root, app_map_path)
    print(f"      Harness: {codegen['harness_path']}")
    print(f"      Runnable screens: {codegen['runnable']}")
    if codegen["skipped"]:
        print(f"      Skipped (manual stubs needed):")
        for s in codegen["skipped"]:
            print(f"        - {s['class']}: {s['reason']}")
    print(f"      Resolutions: {codegen['resolutions']}")

    print(f"[2/4] Running flutter test (this may take 30-90s)...")
    result = run_harness(project_root, backend_logs_dir, cleanup_harness=cleanup)
    print(f"      Captured {result['total_pngs']} PNGs across "
          f"{len(result['screens'])} screens.")

    visual_report = None
    if skip_vision:
        print(f"[3/4] Skipping vision pass (--skip-vision).")
    else:
        print(f"[3/4] Running Gemini Vision analysis on every PNG...")
        screenshots_root = Path(result["screenshots_dir"])
        app_map = json.loads(Path(app_map_path).read_text())
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
        visual_report = analyze_project_screenshots(
            screenshots_root, app_map, plans_by_name,
            existing_report_path=report_path,
        )
        report_path.write_text(json.dumps(visual_report, indent=2, ensure_ascii=False))
        print(f"      {visual_report['total_issues_found']} UI issues found, "
              f"severity {visual_report['severity_counts']}.")

    print(f"[4/4] Done.")
    print()
    print("=" * 70)
    print(f"PNGs:          {result['total_pngs']} at {result['screenshots_dir']}")
    if visual_report is not None:
        print(f"Visual report: backend/logs/visual_report.json "
              f"({visual_report['total_issues_found']} issues)")
    print("=" * 70)


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    skip_vision = "--skip-vision" in sys.argv
    if not args:
        print(__doc__)
        sys.exit(1)
    project = args[0]
    app_map = args[1] if len(args) > 1 else str(
        Path(__file__).parent / "logs" / "app_map.json"
    )
    if not Path(app_map).is_file():
        print(f"App map not found at {app_map}. Run step2_multi_file.py first.")
        sys.exit(1)
    run(project, app_map, skip_vision=skip_vision)


if __name__ == "__main__":
    main()
