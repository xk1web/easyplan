import json
from openai import OpenAI
from scheduler import generate_schedule

client = OpenAI()


def ai_parse_prompt(prompt, employees, days):
    system_message = (
        "You are a scheduling assistant. Given a user prompt, extract which employees "
        "are unavailable on which days. Return a JSON array of objects with 'employee' "
        "and 'day' keys. Only use employees and days from the provided lists.\n\n"
        f"Employees: {json.dumps(employees)}\n"
        f"Days: {json.dumps(days)}\n\n"
        "Example output: [{\"employee\": \"Alice\", \"day\": \"Fri\"}]\n"
        "If no unavailability is mentioned, return an empty array: []"
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
    )

    content = response.choices[0].message.content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    parsed = json.loads(content)

    unavailable = []
    for entry in parsed:
        emp = entry["employee"]
        day = entry["day"]
        if emp in employees and day in days:
            unavailable.append((employees.index(emp), days.index(day)))

    return unavailable


if __name__ == "__main__":
    employees = ["Alice", "Bob", "Charlie"]
    days = ["Mon", "Tue", "Wed", "Thu", "Fri"]

    prompt = "Alice ne travaille pas Fri et Bob ne travaille pas Tue"

    unavailable = ai_parse_prompt(prompt, employees, days)

    schedule = generate_schedule(employees, days, unavailable)

    print("Prompt:", prompt)
    print("Unavailable parsed:", unavailable)
    print("Schedule:", schedule)
