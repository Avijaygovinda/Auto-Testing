"""
Phase 3b — Visual Tester.

For each PNG produced in Phase 3a, send the image plus screen context to
Gemini Vision and collect a JSON UI bug report. Aggregate per-screen and
flag resolution-specific regressions.
"""
import json
import os
import re
import time
from pathlib import Path
from typing import Optional

from google import genai
from google.genai import types
from dotenv import load_dotenv

from ..utils.logger import log_api_call
from ..utils.gemini_retry import call_with_retry


def _load_prompt() -> str:
    return (Path(__file__).parent.parent / "prompts" / "visual_tester.txt").read_text(encoding="utf-8")


def _screen_context_block(screen_name: str, app_map: dict, screen_plans_by_name: dict) -> str:
    """Return a compact context blob the vision model can use."""
    info = next(
        (s for s in app_map.get("screens", []) if s.get("name") == screen_name),
        None,
    )
    plan = screen_plans_by_name.get(screen_name) or {}
    return json.dumps({
        "screen_name": screen_name,
        "screen_file": info.get("file") if info else None,
        "purpose": info.get("purpose") if info else None,
        "depends_on": info.get("depends_on") if info else [],
        "test_focus_summary": plan.get("summary"),
    }, indent=2, ensure_ascii=False)


def analyze_screenshot(
    png_path: Path,
    screen_name: str,
    resolution: str,
    context_block: str,
    *,
    sleep_before: float = 4.0,
) -> dict:
    """Send one PNG to Gemini Vision, return parsed JSON report."""
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not found in env.")

    image_bytes = png_path.read_bytes()
    prompt_text = (
        f"{_load_prompt()}\n\n"
        f"===== SCREEN CONTEXT =====\n{context_block}\n\n"
        f"===== RESOLUTION =====\n{resolution}\n\n"
        f"Now analyze the attached screenshot and return JSON:\n"
    )

    client = genai.Client(api_key=api_key)
    if sleep_before > 0:
        time.sleep(sleep_before)

    response = call_with_retry(
        lambda: client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                prompt_text,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
            ),
        ),
        label=f"visual_tester:{screen_name}@{resolution}",
    )
    text = response.text

    log_api_call(
        model="gemini-2.5-flash",
        prompt=prompt_text,
        response=text,
        metadata={
            "pass": "3b_visual",
            "screen": screen_name,
            "resolution": resolution,
            "image_bytes": len(image_bytes),
        },
    )
    from ..utils import json_repair
    return json_repair.loads(text)


def analyze_project_screenshots(
    screenshots_root: Path,
    app_map: dict,
    screen_plans_by_name: dict,
    *,
    existing_report_path: Optional[Path] = None,
) -> dict:
    """Walk a screenshots/<screen>/<WxH>.png tree and analyze every PNG.

    Returns a top-level visual report dict.
    """
    screenshots_root = Path(screenshots_root)
    if not screenshots_root.is_dir():
        raise FileNotFoundError(f"Screenshots root not found: {screenshots_root}")

    # Build screen-name lookup tolerant of slug forms (home_screen <-> HomeScreen).
    name_lookup = {}
    for s in app_map.get("screens", []):
        n = s.get("name", "")
        slug = re.sub(r"(?<!^)([A-Z])", r"_\1", n).lower()
        name_lookup[slug] = n
        name_lookup[n] = n

    # Load existing report so we can resume after partial quota failures.
    cached: dict[str, dict] = {}
    if existing_report_path and existing_report_path.is_file():
        try:
            prev = json.loads(existing_report_path.read_text())
            for slug, scr in prev.get("screens", {}).items():
                for res, rep in scr.get("reports_by_resolution", {}).items():
                    if "_error" not in rep and rep.get("overall_quality") not in (None, "UNKNOWN"):
                        cached[f"{slug}/{res}"] = rep
            if cached:
                print(f"[visual] resuming — {len(cached)} cached reports will be reused.")
        except (json.JSONDecodeError, OSError):
            pass

    per_screen: dict[str, dict] = {}
    total_issues = 0
    severity_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}

    for screen_dir in sorted(screenshots_root.iterdir()):
        if not screen_dir.is_dir():
            continue
        slug = screen_dir.name
        screen_name = name_lookup.get(slug, slug)
        context = _screen_context_block(screen_name, app_map, screen_plans_by_name)
        per_resolution: dict[str, dict] = {}

        for png in sorted(screen_dir.glob("*.png")):
            resolution = png.stem
            cache_key = f"{slug}/{resolution}"
            if cache_key in cached:
                print(f"[visual] {slug} @ {resolution}: cached, skipping.")
                report = cached[cache_key]
                per_resolution[resolution] = report
                for issue in report.get("issues", []):
                    total_issues += 1
                    sev = issue.get("severity", "MEDIUM")
                    severity_counts[sev] = severity_counts.get(sev, 0) + 1
                continue
            print(f"[visual] {slug} @ {resolution}: analyzing...")
            try:
                report = analyze_screenshot(png, screen_name, resolution, context)
            except Exception as e:
                print(f"[visual] {slug} @ {resolution}: FAILED ({type(e).__name__}: {e})")
                report = {"screen_name": screen_name, "resolution": resolution,
                          "overall_quality": "UNKNOWN", "issues": [],
                          "positive_observations": [], "_error": str(e)}
            per_resolution[resolution] = report
            for issue in report.get("issues", []):
                total_issues += 1
                sev = issue.get("severity", "MEDIUM")
                severity_counts[sev] = severity_counts.get(sev, 0) + 1

        per_screen[slug] = {
            "screen_name": screen_name,
            "resolutions_analyzed": list(per_resolution.keys()),
            "reports_by_resolution": per_resolution,
            "resolution_specific_issues": _flag_resolution_specific(per_resolution),
        }

    return {
        "project": screenshots_root.name,
        "total_screens_analyzed": len(per_screen),
        "total_issues_found": total_issues,
        "severity_counts": severity_counts,
        "screens": per_screen,
    }


def _flag_resolution_specific(per_resolution: dict[str, dict]) -> list[dict]:
    """Find issues present at some resolutions but absent at others."""
    issues_by_res = {res: [i.get("title", "") for i in r.get("issues", [])]
                     for res, r in per_resolution.items()}
    flagged: list[dict] = []
    all_titles: set[str] = set()
    for titles in issues_by_res.values():
        all_titles.update(titles)
    for title in all_titles:
        present = [res for res, titles in issues_by_res.items() if title in titles]
        absent = [res for res in issues_by_res if res not in present]
        if present and absent:
            flagged.append({
                "issue_title": title,
                "present_at": sorted(present),
                "absent_at": sorted(absent),
                "interpretation": "responsive bug — appears only at certain widths",
            })
    return flagged


if __name__ == "__main__":
    import sys
    project = sys.argv[1] if len(sys.argv) > 1 else "movie_browser"
    screenshots_root = Path(f"backend/logs/screenshots/{project}")
    app_map = json.loads(Path("backend/logs/app_map.json").read_text())
    plan_dir = Path("backend/logs/test_plan")
    plans_by_name: dict[str, dict] = {}
    if plan_dir.is_dir():
        for jf in plan_dir.glob("*.json"):
            if jf.name.startswith("_"):
                continue
            data = json.loads(jf.read_text())
            plans_by_name[data.get("screen_name", jf.stem)] = data

    out = Path("backend/logs/visual_report.json")
    report = analyze_project_screenshots(
        screenshots_root, app_map, plans_by_name,
        existing_report_path=out,
    )
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nVisual report saved to {out}")
    print(f"Total issues: {report['total_issues_found']}, severity: {report['severity_counts']}")
