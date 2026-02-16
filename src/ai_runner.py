import json
from scheduler import generate_schedule
from ai_client import client


def ai_parse_prompt(prompt, employees, days):
    system_message = f"""
You are a scheduling assistant.

Extract TWO types of information from the user prompt:

1) Hard unavailability (employee absolutely not working)
2) Soft preferences (employee prefers to avoid a day)

Return STRICT JSON in this format:

{{
  "unavailable": [["EmployeeName", "Day"]],
  "preferences": [
      {{"employee": "EmployeeName", "day": "Day", "weight": 5}}
  ]
}}

Only use these employees:
{employees}

Only use these days:
{days}

If nothing is found, return:
{{
  "unavailable": [],
  "preferences": []
}}

Do NOT include any text outside JSON.
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"}
    )

    result = json.loads(response.choices[0].message.content)

    unavailable_pairs = []
    preference_tuples = []

    # Hard constraints
    for emp_name, day_name in result.get("unavailable", []):
        if emp_name in employees and day_name in days:
            emp_index = employees.index(emp_name)
            day_index = days.index(day_name)
            unavailable_pairs.append((emp_index, day_index))

    # Soft constraints
    for pref in result.get("preferences", []):
        emp_name = pref.get("employee")
        day_name = pref.get("day")
        weight = pref.get("weight", 1)

        if emp_name in employees and day_name in days:
            emp_index = employees.index(emp_name)
            day_index = days.index(day_name)
            preference_tuples.append((emp_index, day_index, weight))

    return unavailable_pairs, preference_tuples


if __name__ == "__main__":
    employees = ["Alice", "Bob", "Charlie"]
    days = ["Mon", "Tue", "Wed", "Thu", "Fri"]

    prompt = "Bob préfère éviter vendredi"

    unavailable, preferences = ai_parse_prompt(prompt, employees, days)

    contracts = [40, 20, 40]
    coverage_per_day = [2, 2, 2, 2, 2]
    roles = ["opticien", "vendeur", "opticien"]
    required_opticians_per_day = 1

    schedule = generate_schedule(
        employees,
        days,
        unavailable,
        contracts,
        coverage_per_day,
        roles,
        required_opticians_per_day,
        preferences
    )

    print("Prompt:", prompt)
    print("Unavailable parsed:", unavailable)
    print("Preferences parsed:", preferences)
    print("Schedule:", schedule)
