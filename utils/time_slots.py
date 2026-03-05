from typing import List, Union


TimeValue = Union[int, str]


def _to_minutes(value: TimeValue) -> int:
    if isinstance(value, int):
        return value
    hh, mm = value.split(":", 1)
    return int(hh) * 60 + int(mm)


def generate_opening_slots(
    open_time: TimeValue,
    close_time: TimeValue,
    slot_minutes: int = 15,
) -> List[int]:
    open_minutes = _to_minutes(open_time)
    close_minutes = _to_minutes(close_time)
    if close_minutes <= open_minutes:
        raise ValueError("close_time must be after open_time.")
    if (close_minutes - open_minutes) % slot_minutes != 0:
        raise ValueError("Opening range is incompatible with slot_minutes.")

    slots = list(range((close_minutes - open_minutes) // slot_minutes))
    print("SLOT GENERATION DEBUG")
    print("open:", open_minutes)
    print("close:", close_minutes)
    print("slot_minutes:", slot_minutes)
    print("slots_generated:", len(slots))
    return slots


def time_to_slot(hhmm: str, start_time_minutes: int = 0, slot_minutes: int = 15) -> int:
    hh, mm = hhmm.split(":", 1)
    minutes = int(hh) * 60 + int(mm)
    relative = minutes - start_time_minutes
    if relative <= 0:
        return 0
    return relative // slot_minutes
