"""
FlowTest AI — master driver
===========================
Runs Phase 2 (logic test plan) + Phase 3 (simulated visual) + Phase 4
(real-device visual) end-to-end on a single Flutter project.

Phase 1 is the single-file prototype and is not part of the per-project
pipeline; skipped here.

Usage:
    python run_all.py <project_root> [<doc_file>]

Example:
    python run_all.py /Users/me/projects/task_manager

If <doc_file> is omitted, defaults to <project_root>/README.md.

Flags:
    --skip-phase3       Skip simulated multi-resolution screenshots.
    --skip-phase4       Skip real-device run (set if no device connected).
    --skip-vision       Capture screenshots but don't call Gemini Vision.

Output (in backend/logs/):
    app_map.json
    test_plan/<screen>.json + _flows.json + _app_plan.json
    screenshots/<project>/                (Phase 3)
    screenshots/<project>_real/           (Phase 4)
    visual_report.json                    (merged across phases via cache)
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.step2_multi_file import run as run_phase2
from backend.step4_v2 import run as run_phase4_v2
from backend.agents.realdevice_v2.runner import _detect_device


_BAR = "=" * 70


def _banner(title: str) -> None:
    print()
    print(_BAR)
    print(f"  {title}")
    print(_BAR)


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    skip_phase3 = "--skip-phase3" in sys.argv
    skip_phase4 = "--skip-phase4" in sys.argv
    skip_vision = "--skip-vision" in sys.argv

    if not args:
        print(__doc__)
        sys.exit(1)

    project = Path(args[0]).resolve()
    if not (project / "lib").is_dir():
        print(f"ERROR: {project} is not a Flutter project (no lib/ folder).")
        sys.exit(1)

    doc = Path(args[1]) if len(args) > 1 else project / "README.md"
    if not doc.is_file():
        print(f"ERROR: doc file not found: {doc}")
        sys.exit(1)

    backend_dir = Path(__file__).parent
    app_map_path = backend_dir / "logs" / "app_map.json"

    started = time.time()

    _banner("PHASE 2 — code analysis & logic test plan")
    run_phase2(str(project), str(doc))

    # Phase 3 (simulated widget-test screenshots) is intentionally NOT run by
    # default. v2 supersedes it with real-device runs that have real API data.
    # Pass --include-phase3 to opt in for legacy behavior.
    if "--include-phase3" in sys.argv:
        from backend.step3_visual import run as run_phase3
        _banner("PHASE 3 (legacy) — simulated multi-resolution screenshots")
        try:
            run_phase3(str(project), str(app_map_path), skip_vision=skip_vision)
        except Exception as e:
            print(f"\n[Phase 3 FAILED] {type(e).__name__}: {e}")

    if skip_phase4:
        print("\n[skipped] Phase 4 v2 — real device.")
    else:
        _banner("PHASE 4 v2 — real device + AI navigation + HITL")
        device = _detect_device()
        if not device:
            print("[Phase 4 SKIPPED] No connected device found via `adb devices`.")
            print("Plug in phone with USB debugging or `adb connect <ip>:5555`, then re-run.")
        else:
            try:
                run_phase4_v2(str(project), str(doc), skip_vision=skip_vision)
            except Exception as e:
                print(f"\n[Phase 4 v2 FAILED] {type(e).__name__}: {e}")

    elapsed = time.time() - started
    _banner(f"ALL DONE — {elapsed:.0f}s elapsed")
    print(f"App map:        backend/logs/app_map.json")
    print(f"Test plan:      backend/logs/test_plan/_app_plan.json")
    print(f"Screenshots:    backend/logs/screenshots/")
    print(f"Visual report:  backend/logs/visual_report.json")
    print(_BAR)


if __name__ == "__main__":
    main()
