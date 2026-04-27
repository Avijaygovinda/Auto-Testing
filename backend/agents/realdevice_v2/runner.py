"""
Runner — boots the host HTTP server, sets up `adb reverse` so the device
test can reach the Mac, runs `flutter test` in a subprocess, and tears
everything down.

After the run, hands the harvested PNGs to the existing visual_tester
(Phase 3b machinery, reused).
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from .codegen import generate_harness, HARNESS_PATH
from .server import HostServer


def _detect_device(adb_bin: str = "adb") -> Optional[str]:
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


def _adb_reverse(device: str, port: int, adb_bin: str = "adb") -> None:
    """Make device-side localhost:<port> reach Mac's localhost:<port>."""
    subprocess.run([adb_bin, "-s", device, "reverse", f"tcp:{port}", f"tcp:{port}"],
                   check=True, capture_output=True)


def _adb_reverse_clear(device: str, port: int, adb_bin: str = "adb") -> None:
    subprocess.run([adb_bin, "-s", device, "reverse", "--remove", f"tcp:{port}"],
                   capture_output=True)


def _load_test_creds() -> dict[str, str]:
    """Pull all FLUTTER_TEST_* env vars into a dict so the AI can use them."""
    creds: dict[str, str] = {}
    for k, v in os.environ.items():
        if k.startswith("FLUTTER_TEST_"):
            creds[k] = v
    return creds


def run_on_device(
    project_root: str | Path,
    backend_logs_dir: str | Path,
    *,
    app_map: dict,
    documentation: str,
    flutter_bin: str = "flutter",
    adb_bin: str = "adb",
    port: int = 5000,
    timeout_seconds: int = 1500,
) -> dict:
    project_root = Path(project_root).resolve()
    backend_logs_dir = Path(backend_logs_dir).resolve()

    device = _detect_device(adb_bin)
    if not device:
        raise RuntimeError(
            "No connected device. Plug in phone with USB debugging on, "
            "or `adb connect <ip>:5555` for wireless adb."
        )

    print(f"[runner] device: {device}")
    print(f"[runner] codegen: writing integration_test harness…")
    cg = generate_harness(project_root, app_map, port=port)
    print(f"[runner]   harness: {cg['harness_path']}")
    print(f"[runner]   targets: {cg['target_screens']}")
    if cg["pubspec_modified"]:
        print(f"[runner]   pubspec.yaml modified — running flutter pub get")
        subprocess.run([flutter_bin, "pub", "get"], cwd=str(project_root), check=True)

    project_slug = project_root.name + "_v2"
    screenshots_dir = backend_logs_dir / "screenshots" / project_slug
    if screenshots_dir.exists():
        shutil.rmtree(screenshots_dir)
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    server = HostServer(
        port=port,
        screenshots_dir=screenshots_dir,
        app_map=app_map,
        documentation=documentation,
        test_creds=_load_test_creds(),
    )
    server.start()

    try:
        _adb_reverse(device, port, adb_bin)
        print(f"[runner] adb reverse tcp:{port} -> Mac localhost:{port}")

        print(f"[runner] flutter test {HARNESS_PATH} -d {device} (10–20 min wall time)")
        proc = subprocess.run(
            [flutter_bin, "test", HARNESS_PATH, "-d", device, "--reporter=compact"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        log = proc.stdout + "\n" + proc.stderr
        ok = proc.returncode == 0
        if not ok:
            tail = "\n".join(log.strip().splitlines()[-30:])
            print(f"[runner] flutter test FAILED. Tail:\n{tail}")
    finally:
        _adb_reverse_clear(device, port, adb_bin)
        server.stop()

    manifest = {
        "ok": ok,
        "device": device,
        "project": project_slug,
        "screenshots_dir": str(screenshots_dir),
        "saved_pngs": server.saved_pngs,
        "flutter_errors": server.flutter_errors,
        "events": list(server.events)[-200:],  # last 200 for sanity
        "flutter_test_returncode": proc.returncode,
    }
    (screenshots_dir / "_manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest
