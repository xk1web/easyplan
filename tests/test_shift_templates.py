import unittest

from model.shift_templates import SHIFT_TEMPLATES, build_template_slots, compute_template_time


class TestShiftTemplates(unittest.TestCase):
    def test_templates_generate_non_empty_slots_with_min_duration(self):
        open_time = "10:30"
        close_time = "19:00"
        slots_by_template = build_template_slots(open_time, close_time, slot_minutes=15)

        self.assertTrue(slots_by_template)
        for name, template in SHIFT_TEMPLATES.items():
            start_time, end_time = compute_template_time(template, open_time, close_time)
            duration_minutes = end_time - start_time
            self.assertGreaterEqual(duration_minutes, 6 * 60, f"{name} must be >= 6h")

            slots = slots_by_template.get(name, [])
            self.assertTrue(slots, f"{name} should produce non-empty slots")


if __name__ == "__main__":
    unittest.main()
