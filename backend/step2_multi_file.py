"""
FlowTest AI — Phase 2 Driver
============================
End-to-end multi-file analysis. Walks a Flutter project, builds an app map,
generates per-screen test plans, and writes one consolidated app plan.

Usage:
    python step2_multi_file.py <project_root> <doc_file>

Example:
    python step2_multi_file.py ../sample-flutter-app ../docs/sample-doc.md

Output:
    backend/logs/app_map.json
    backend/logs/test_plan/<screen>.json   (one per screen)
    backend/logs/test_plan/_app_plan.json  (consolidated)
"""
import json
import sys
from pathlib import Path

# Make package imports work whether run as `python step2_multi_file.py` or
# `python -m backend.step2_multi_file`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.agents.codebase_scanner import scan_flutter_project
from backend.agents.file_classifier import classify_all
from backend.agents.app_mapper import map_app
from backend.agents.screen_tester import test_screen
from backend.agents.flow_tester import test_flows
from backend.agents.test_plan_builder import write_app_plan


def run(project_root: str, doc_path: str) -> None:
    logs_dir = Path(__file__).parent / "logs"
    plan_dir = logs_dir / "test_plan"
    logs_dir.mkdir(exist_ok=True)
    plan_dir.mkdir(exist_ok=True)

    print(f"[1/5] Scanning Flutter project at {project_root}...")
    files = classify_all(scan_flutter_project(project_root))
    print(f"      Found {len(files)} dart files.")
    by_path = {f.rel_path: f for f in files}

    documentation = Path(doc_path).read_text(encoding="utf-8")

    print(f"[2/5] Pass A: building app map...")
    app_map = map_app(files, documentation)
    (logs_dir / "app_map.json").write_text(json.dumps(app_map, indent=2, ensure_ascii=False))
    print(f"      Detected {len(app_map.get('screens', []))} screens, "
          f"{len(app_map.get('key_flows', []))} flows, "
          f"{len(app_map.get('open_questions', []))} open questions.")

    screens = [f for f in files if "screen" in f.tags]
    print(f"[3/5] Pass B: generating test plans for {len(screens)} screens...")
    screen_plans: list[dict] = []
    for sc in screens:
        plan = test_screen(sc, by_path, app_map, documentation)
        slug = Path(sc.rel_path).stem
        (plan_dir / f"{slug}.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False))
        screen_plans.append(plan)
        print(f"      {slug}: {len(plan.get('test_cases', []))} cases, "
              f"{len(plan.get('questions_for_developer', []))} questions.")

    print(f"[4/5] Pass C: generating end-to-end flow tests...")
    flow_plan: dict | None = None
    try:
        flow_plan = test_flows(app_map, screen_plans, documentation)
        (plan_dir / "_flows.json").write_text(json.dumps(flow_plan, indent=2, ensure_ascii=False))
        print(f"      {len(flow_plan.get('flow_test_cases', []))} flow cases, "
              f"{len(flow_plan.get('questions_for_developer', []))} questions.")
    except Exception as e:
        print(f"      WARNING: flow_tester failed ({type(e).__name__}: {e}). "
              f"Continuing without flow cases.")

    print(f"[5/5] Aggregating into consolidated app plan...")
    app_plan_path = write_app_plan(plan_dir, app_map, screen_plans, flow_plan)
    final = json.loads(app_plan_path.read_text())

    print()
    print("=" * 70)
    print(f"DONE. {final['total_test_cases']} total cases "
          f"({final['total_screen_test_cases']} screen + "
          f"{final['total_flow_test_cases']} flow) "
          f"across {final['total_screens']} screens.")
    print(f"Consolidated questions for developer: "
          f"{len(final['consolidated_questions_for_developer'])}")
    print(f"Output: {app_plan_path}")
    print("=" * 70)


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    run(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    main()
