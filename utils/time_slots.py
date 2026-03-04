def time_to_slot(hhmm: str, start_time_minutes: int = 0, slot_minutes: int = 15) -> int:
    hh, mm = hhmm.split(":", 1)
    minutes = int(hh) * 60 + int(mm)
    relative = minutes - start_time_minutes
    if relative <= 0:
        return 0
    return relative // slot_minutes
