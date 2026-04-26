"""
Phase 3a — runs the generated Dart harness via `flutter test` and harvests
the produced PNGs into our backend/logs/screenshots/<project>/<screen>/<WxH>.png.

No AI. Pure subprocess + filesystem.
"""
import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional


HARNESS_OUTPUT_SUBDIR = "test/_flowtest_screenshots"


def _pretty_tail(stream: str, n: int = 40) -> str:
    lines = stream.strip().splitlines()
    return "\n".join(lines[-n:])


def run_harness(
    project_root: str | Path,
    backend_logs_dir: str | Path,
    *,
    harness_relpath: str = "test/_flowtest_screenshots_test.dart",
    cleanup_harness: bool = False,
    flutter_bin: str = "flutter",
    timeout_seconds: int = 600,
) -> dict:
    """Run `flutter test <harness>` and copy the PNGs to backend/logs/screenshots/.

    Returns dict summary: {ok, screens, total_pngs, log_dir, harness_kept}.
    """
    project_root = Path(project_root).resolve()
    backend_logs_dir = Path(backend_logs_dir).resolve()

    harness = project_root / harness_relpath
    if not harness.is_file():
        raise FileNotFoundError(f"Harness not generated: {harness}")

    # `flutter test` MUST run from the project root so it can resolve pubspec.
    print(f"[runner] flutter test {harness_relpath} (cwd={project_root})")
    proc = subprocess.run(
        [flutter_bin, "test", harness_relpath, "--reporter=compact"],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )

    ok = proc.returncode == 0
    if not ok:
        print("[runner] flutter test FAILED. Tail of output:")
        print(_pretty_tail(proc.stdout + "\n" + proc.stderr))

    # Even partial runs may have produced some PNGs — harvest whatever exists.
    src_root = project_root / HARNESS_OUTPUT_SUBDIR
    project_slug = project_root.name
    dest_root = backend_logs_dir / "screenshots" / project_slug
    if dest_root.exists():
        shutil.rmtree(dest_root)
    dest_root.mkdir(parents=True, exist_ok=True)

    screens_summary: dict[str, list[str]] = {}
    total = 0
    if src_root.is_dir():
        for screen_dir in sorted(src_root.iterdir()):
            if not screen_dir.is_dir():
                continue
            target = dest_root / screen_dir.name
            target.mkdir(parents=True, exist_ok=True)
            pngs = []
            for png in sorted(screen_dir.glob("*.png")):
                shutil.copy2(png, target / png.name)
                pngs.append(png.name)
                total += 1
            screens_summary[screen_dir.name] = pngs

    # Optional cleanup of harness + artifacts inside target project.
    harness_kept = True
    if cleanup_harness:
        try:
            harness.unlink(missing_ok=True)
            if src_root.is_dir():
                shutil.rmtree(src_root)
            harness_kept = False
        except OSError:
            pass

    manifest = {
        "ok": ok,
        "project": project_slug,
        "screens": screens_summary,
        "total_pngs": total,
        "screenshots_dir": str(dest_root),
        "harness_kept_in_project": harness_kept,
        "flutter_test_returncode": proc.returncode,
    }
    (dest_root / "_manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


if __name__ == "__main__":
    import sys
    proj = sys.argv[1]
    out = run_harness(proj, backend_logs_dir="backend/logs")
    print(json.dumps(out, indent=2))
