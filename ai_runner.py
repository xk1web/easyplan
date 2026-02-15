from scheduler import generate_schedule


def parse_prompt(prompt, employees, days):
    """
    Version simple : détecte des phrases du type
    'Alice ne travaille pas Fri'
    """
    unavailable = []

    words = prompt.split()

    for emp in employees:
        if emp in words:
            for day in days:
                if day in words:
                    emp_index = employees.index(emp)
                    day_index = days.index(day)
                    unavailable.append((emp_index, day_index))

    return unavailable


if __name__ == "__main__":
    employees = ["Alice", "Bob", "Charlie"]
    days = ["Mon", "Tue", "Wed", "Thu", "Fri"]

    prompt = "Alice ne travaille pas Fri"

    unavailable = parse_prompt(prompt, employees, days)

    schedule = generate_schedule(employees, days, unavailable)

    print("Prompt:", prompt)
    print("Schedule:", schedule)
