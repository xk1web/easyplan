from scheduler import generate_schedule


def parse_prompt(prompt, employees, days):
    unavailable = []

    # Séparer les phrases par "et"
    parts = prompt.split("et")

    for part in parts:
        part_lower = part.lower()

        found_employee = None
        found_day = None

        for emp in employees:
            if emp.lower() in part_lower:
                found_employee = emp

        for day in days:
            if day.lower() in part_lower:
                found_day = day

        if found_employee and found_day:
            emp_index = employees.index(found_employee)
            day_index = days.index(found_day)
            unavailable.append((emp_index, day_index))

    return unavailable


if __name__ == "__main__":
    employees = ["Alice", "Bob", "Charlie"]
    days = ["Mon", "Tue", "Wed", "Thu", "Fri"]

    prompt = "Alice ne travaille pas Fri et Bob ne travaille pas Tue"

    unavailable = parse_prompt(prompt, employees, days)

    schedule = generate_schedule(employees, days, unavailable)

    print("Prompt:", prompt)
    print("Unavailable parsed:", unavailable)
    print("Schedule:", schedule)
