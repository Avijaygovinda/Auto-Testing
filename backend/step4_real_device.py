"""
FlowTest AI — Phase 4 Driver: real-device visual testing
========================================================
Drives a connected Android device via integration_test, navigating each
screen with real API calls, and feeds the resulting PNGs into the existing
Gemini Vision pass (Phase 3b).

Phase 3 covers multi-resolution simulated tests (widget tests, no real data).
Phase 4 covers single-resolution real-data tests on a real device. Use both
together for the most thorough visual coverage.

Usage:
    python step4_real_device.py <project_root> [<app_map.json>]

Example:
    python step4_real_device.py /Users/me/projects/movie_browser

Output:
    backend/logs/screenshots/<project>_real/<screen>/native.png
    backend/logs/visual_report.json (merged with prior runs via cache)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.agents.realdevice_codegen import generate_harness
from backend.agents.realdevice_runner import run_on_device
from backend.agents.visual_tester import analyze_project_screenshots


def run(project_root: str, app_map_path: str, *, skip_vision: bool = False) -> None:
    backend_logs_dir = Path(__file__).parent / "logs"
    backend_logs_dir.mkdir(exist_ok=True)

    print(f"[1/3] Generating integration_test harness for {project_root}...")
    codegen = generate_harness(project_root, app_map_path)
    print(f"      Harness: {codegen['harness_path']}")
    print(f"      Package: {codegen['package']}")
    print(f"      App root: {codegen['app_root']}")
    print(f"      Screens: {codegen['screens']}")
    if codegen["pubspec_modified"]:
        print("      pubspec.yaml updated — adding integration_test dev dep.")
        print("      Run `flutter pub get` in the target project before continuing.")

    print(f"[2/3] Running flutter test on connected device (this may take 3-8 minutes)...")
    result = run_on_device(project_root, backend_logs_dir)
    print(f"      Device: {result['device']}")
    print(f"      Captured {result['total_pngs']} PNGs across "
          f"{len(result['screens'])} screens.")
    if not result["ok"]:
        print(f"      WARNING: flutter test returncode={result['flutter_test_returncode']}.")

    visual_report = None
    if skip_vision:
        print(f"[3/3] Skipping vision pass (--skip-vision).")
    else:
        print(f"[3/3] Running Gemini Vision analysis on every PNG...")
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
