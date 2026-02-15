from scheduler import generate_schedule


def parse_prompt(prompt, employees, days):
    unavailable = []
    prompt_lower = prompt.lower()

    for emp in employees:
        if emp.lower() in prompt_lower:
            for day in days:
                if day.lower() in prompt_lower:
                    emp_index = employees.index(emp)
                    day_index = days.index(day)
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
