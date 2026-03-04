from __future__ import annotations

from typing import Dict, Iterable, List, Tuple, Union


TimeValue = Union[int, str]

MIN_SHIFT_MINUTES = 6 * 60
CLOSING_TEMPLATES = [
    "CLOSING_LONG",
    "FULL_LATE",
]

SHIFT_TEMPLATES: Dict[str, Dict[str, Union[int, str]]] = {
    # Tier 1 — journees dominantes
    "FULL_OPEN": {
        "start_offset": 0,
        "end_offset": 0,
        "pause_minutes": 60,
        "anchor": "open_close",
        "tier": 1,
    },
    "MIDDAY": {
        "start_offset": 60,
        "end_offset": -60,
        "pause_minutes": 60,
        "anchor": "open_close",
        "tier": 1,
    },
    "FULL_LATE": {
        "start_offset": 90,
        "end_offset": 0,
        "pause_minutes": 60,
        "anchor": "close",
        "tier": 1,
    },
    "FULL_EARLY": {
        "start_offset": 0,
        "end_offset": -90,
        "pause_minutes": 60,
        "anchor": "open",
        "tier": 1,
    },
    # Tier 2 — journees normales
    "OPENING_LONG": {
        "start_offset": 0,
        "duration_hours": 7,
        "pause_minutes": 60,
        "anchor": "open",
        "tier": 2,
    },
    "CLOSING_LONG": {
        "duration_hours": 7,
        "end_offset": 0,
        "pause_minutes": 60,
        "anchor": "close",
        "tier": 2,
    },
    "MID_LONG": {
        "start_offset": 120,
        "duration_hours": 7,
        "pause_minutes": 60,
        "anchor": "open",
        "tier": 2,
    },
    # Tier 3 — journees plus courtes
    "SHORT_AM": {
        "start_offset": 0,
        "duration_hours": 6,
        "pause_minutes": 0,
        "anchor": "open",
        "tier": 3,
    },
    "SHORT_PM": {
        "duration_hours": 6,
        "end_offset": 0,
        "pause_minutes": 0,
        "anchor": "close",
        "tier": 3,
    },
    "SHORT_MID": {
        "start_offset": 120,
        "duration_hours": 6,
        "pause_minutes": 0,
        "anchor": "open",
        "tier": 3,
    },
}


def _to_minutes(time_value: TimeValue) -> int:
    if isinstance(time_value, int):
        return time_value
    if isinstance(time_value, str):
        hh, mm = time_value.split(":", 1)
        return int(hh) * 60 + int(mm)
    raise TypeError(f"Unsupported time format: {time_value!r}")


def compute_template_time(template: Dict[str, Union[int, str]], open_time: TimeValue, close_time: TimeValue) -> Tuple[int, int]:
    open_minutes = _to_minutes(open_time)
    close_minutes = _to_minutes(close_time)
    if close_minutes <= open_minutes:
        raise ValueError("close_time must be after open_time.")

    anchor = str(template.get("anchor", "open_close"))
    start_offset = int(template.get("start_offset", 0))
    end_offset = int(template.get("end_offset", 0))
    duration_hours = template.get("duration_hours")
    duration_minutes = int(duration_hours) * 60 if duration_hours is not None else None
    pause_minutes = int(template.get("pause_minutes", 0))

    if anchor == "open_close":
        start_time = open_minutes + start_offset
        end_time = close_minutes + end_offset
    elif anchor == "open":
        start_time = open_minutes + start_offset
        if duration_minutes is not None:
            end_time = start_time + duration_minutes
        else:
            end_time = close_minutes + end_offset
    elif anchor == "close":
        end_time = close_minutes + end_offset
        if duration_minutes is not None:
            start_time = end_time - duration_minutes
        else:
            start_time = open_minutes + start_offset
    else:
        raise ValueError(f"Unknown template anchor: {anchor}")

    # Adapt templates to store window while preserving duration when possible.
    if duration_minutes is not None:
        if end_time > close_minutes:
            overflow = end_time - close_minutes
            end_time -= overflow
            start_time -= overflow
        if start_time < open_minutes:
            deficit = open_minutes - start_time
            start_time += deficit
            end_time += deficit

    start_time = max(start_time, open_minutes)
    end_time = min(end_time, close_minutes)

    if end_time <= start_time:
        raise ValueError("Template end_time must be after start_time.")
    worked_minutes = (end_time - start_time) - pause_minutes
    if worked_minutes < MIN_SHIFT_MINUTES:
        raise ValueError("Template duration must be at least 6 hours.")

    return start_time, end_time


def template_to_slots(start_time: int, end_time: int, slot_minutes: int = 15, pause_minutes: int = 0) -> List[int]:
    if slot_minutes <= 0:
        raise ValueError("slot_minutes must be > 0")
    if start_time < 0 or end_time <= start_time:
        raise ValueError("Invalid [start_time, end_time] interval")
    if start_time % slot_minutes != 0 or end_time % slot_minutes != 0:
        raise ValueError("Template interval must align with slot_minutes")

    all_slots = list(range(start_time // slot_minutes, end_time // slot_minutes))
    if pause_minutes <= 0:
        return all_slots
    if pause_minutes % slot_minutes != 0:
        raise ValueError("pause_minutes must align with slot_minutes")

    pause_slots = pause_minutes // slot_minutes
    if pause_slots <= 0 or pause_slots >= len(all_slots):
        return all_slots

    # Center the break inside the shift window.
    break_start_idx = (len(all_slots) - pause_slots) // 2
    break_end_idx = break_start_idx + pause_slots
    return all_slots[:break_start_idx] + all_slots[break_end_idx:]


def build_template_slots(open_time: TimeValue, close_time: TimeValue, slot_minutes: int = 15) -> Dict[str, List[int]]:
    open_minutes = _to_minutes(open_time)
    close_minutes = _to_minutes(close_time)

    template_slots: Dict[str, List[int]] = {}
    for name, template in SHIFT_TEMPLATES.items():
        start_time, end_time = compute_template_time(template, open_minutes, close_minutes)
        pause_minutes = int(template.get("pause_minutes", 0))
        relative_start = start_time - open_minutes
        relative_end = end_time - open_minutes
        template_slots[name] = template_to_slots(
            relative_start,
            relative_end,
            slot_minutes=slot_minutes,
            pause_minutes=pause_minutes,
        )
    print("SHIFT_BREAKS_ENABLED")
    return template_slots


def iter_templates_by_tier(templates: Dict[str, Dict[str, Union[int, str]]] = SHIFT_TEMPLATES) -> Iterable[Tuple[str, Dict[str, Union[int, str]]]]:
    return iter(sorted(templates.items(), key=lambda item: (int(item[1].get("tier", 99)), item[0])))
