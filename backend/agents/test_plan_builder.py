"""
Aggregator — combines the app map and every per-screen plan into one
top-level test plan document. Pure Python, no AI call.

Output (backend/logs/test_plan/_app_plan.json) is what a developer or a later
phase (Phase 3+ execution layer) would consume.
"""
import json
from pathlib import Path
from typing import List


def build_app_plan(app_map: dict, screen_plans: List[dict]) -> dict:
    """Merge app map + per-screen plans into one document."""
    total_cases = sum(len(p.get("test_cases", [])) for p in screen_plans)

    screens_index = []
    all_questions: list[str] = []
    seen_questions: set[str] = set()

    for plan in screen_plans:
        cases = plan.get("test_cases", [])
        priority_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
        category_counts: dict[str, int] = {}
        for tc in cases:
            priority_counts[tc.get("priority", "MEDIUM")] = (
                priority_counts.get(tc.get("priority", "MEDIUM"), 0) + 1
            )
            cat = tc.get("category", "OTHER")
            category_counts[cat] = category_counts.get(cat, 0) + 1

        screens_index.append({
            "screen_name": plan.get("screen_name"),
            "screen_file": plan.get("screen_file"),
            "summary": plan.get("summary"),
            "test_case_count": len(cases),
            "priority_counts": priority_counts,
            "category_counts": category_counts,
        })

        for q in plan.get("questions_for_developer", []):
            key = q.strip().lower()
            if key and key not in seen_questions:
                seen_questions.add(key)
                all_questions.append(q.strip())

    # Carry forward app-map-level questions too.
    for q in app_map.get("open_questions", []):
        key = q.strip().lower()
        if key and key not in seen_questions:
            seen_questions.add(key)
            all_questions.append(q.strip())

    return {
        "app_summary": app_map.get("app_summary"),
        "total_screens": len(screen_plans),
        "total_test_cases": total_cases,
        "screens": screens_index,
        "navigation": app_map.get("navigation", []),
        "key_flows": app_map.get("key_flows", []),
        "cross_cutting_concerns": app_map.get("cross_cutting_concerns", []),
        "consolidated_questions_for_developer": all_questions,
    }


def write_app_plan(out_dir: Path, app_map: dict, screen_plans: List[dict]) -> Path:
    plan = build_app_plan(app_map, screen_plans)
    out_path = out_dir / "_app_plan.json"
    out_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False))
    return out_path
