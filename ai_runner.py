import json
import os
from scheduler import generate_schedule
from openai import OpenAI

client = OpenAI(
    api_key=os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY"),
    base_url=os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL"),
)


def ai_parse_prompt(prompt, employees, days):
    system_message = f"""
You are a scheduling assistant.

Extract employee unavailability from the user prompt.

Return STRICT JSON in this format:
{{
  "unavailable": [["EmployeeName", "Day"]]
}}

Only include names from this list:
Employees: {employees}
Days: {days}

If nothing is found, return:
{{ "unavailable": [] }}

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

    for emp_name, day_name in result.get("unavailable", []):
        if emp_name in employees and day_name in days:
            emp_index = employees.index(emp_name)
            day_index = days.index(day_name)
            unavailable_pairs.append((emp_index, day_index))

    return unavailable_pairs


if __name__ == "__main__":
    employees = ["Alice", "Bob", "Charlie"]
    days = ["Mon", "Tue", "Wed", "Thu", "Fri"]

    prompt = "Alice est en congé vendredi et Bob ne travaille pas mardi"

    unavailable = ai_parse_prompt(prompt, employees, days)

    contracts = [35, 20, 35]  # Alice 35h, Bob 20h, Charlie 35h
    schedule = generate_schedule(employees, days, unavailable, contracts)


    print("Prompt:", prompt)
    print("Unavailable parsed:", unavailable)
    print("Schedule:", schedule)
