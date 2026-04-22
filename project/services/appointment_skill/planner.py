from __future__ import annotations

from collections import OrderedDict


def suggest_alternative_doctors(doctor_options: list[dict], *, exclude_name: str = "") -> list[dict]:
    alternatives = []
    exclude = str(exclude_name or "").strip().lower()
    for item in doctor_options or []:
        doctor_name = str(item.get("doctor_name") or "").strip()
        if exclude and doctor_name.lower() == exclude:
            continue
        alternatives.append(item)
    return alternatives


def suggest_alternative_slots(upcoming_rows: list[dict], *, limit: int = 4) -> list[dict]:
    seen = OrderedDict()
    for item in upcoming_rows or []:
        key = (item.get("schedule_date"), item.get("time_slot"), item.get("doctor_name"))
        if key in seen:
            continue
        seen[key] = item
        if len(seen) >= limit:
            break
    return list(seen.values())
