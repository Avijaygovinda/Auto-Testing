"""
Phase 4 — runs the generated integration_test on a connected device, scrapes
the chunked-base64 PNG stream from stdout, and writes per-screen PNG files
into backend/logs/screenshots/<project>_real/.
"""
import base64
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional


CHUNK_RE = re.compile(r"FLOWTEST_PNG_CHUNK:([^:]+):(.+)$")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _detect_device(adb_bin: str = "adb") -> Optional[str]:
    """Return first connected device serial. None if no device attached."""
    try:
        out = subprocess.run([adb_bin, "devices"], capture_output=True, text=True,
                             timeout=10).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    for line in out.splitlines()[1:]:
        line = line.strip()
        if not line or line.endswith("offline"):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            return parts[0]
    return None


def run_on_device(
    project_root: str | Path,
    backend_logs_dir: str | Path,
    *,
    harness_relpath: str = "integration_test/_flowtest_real_device_test.dart",
    flutter_bin: str = "flutter",
    adb_bin: str = "adb",
    timeout_seconds: int = 900,
    device_id: Optional[str] = None,
) -> dict:
    project_root = Path(project_root).resolve()
    backend_logs_dir = Path(backend_logs_dir).resolve()

    device_id = device_id or _detect_device(adb_bin)
    if not device_id:
        raise RuntimeError("No connected device found via `adb devices`. "
                           "Plug in a phone with USB debugging enabled, or "
                           "boot an emulator, before running Phase 4.")

    print(f"[runner] flutter test {harness_relpath} -d {device_id}")
    proc = subprocess.run(
        [flutter_bin, "test", harness_relpath, "-d", device_id],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    log = ANSI_RE.sub("", proc.stdout + proc.stderr)

    # Decode base64 chunks into PNGs.
    chunks: dict[str, list[str]] = {}
    for line in log.splitlines():
        m = CHUNK_RE.search(line.lstrip())
        if m:
            name, chunk = m.group(1), m.group(2).strip()
            chunks.setdefault(name, []).append(chunk)

    project_slug = project_root.name + "_real"
    out_root = backend_logs_dir / "screenshots" / project_slug
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    saved: dict[str, list[str]] = {}
    total = 0
    for name, parts in chunks.items():
        # Convention: "<screen_slug>_<resolution>"
        m = re.match(r"^(.*)_([^_]+)$", name)
        if not m:
            continue
        screen, resolution = m.group(1), m.group(2)
        screen_dir = out_root / screen
        screen_dir.mkdir(parents=True, exist_ok=True)
        try:
            raw = base64.b64decode("".join(parts))
        except Exception as e:
            print(f"[runner] decode failed for {name}: {e}")
            continue
        png_path = screen_dir / f"{resolution}.png"
        png_path.write_bytes(raw)
        saved.setdefault(screen, []).append(resolution)
        total += 1

    return {
        "ok": proc.returncode == 0,
        "device": device_id,
        "project": project_slug,
        "screens": saved,
        "total_pngs": total,
        "screenshots_dir": str(out_root),
        "flutter_test_returncode": proc.returncode,
    }
