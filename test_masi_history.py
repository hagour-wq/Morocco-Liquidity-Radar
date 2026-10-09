import unittest
from pathlib import Path
from collect_masi_history import parse_resume, validate

TEXT = Path("tests/fixtures/resume_seance_20261005.txt").read_text(encoding="utf-8")


class ResumeSeanceTests(unittest.TestCase):
    def test_parse_real_resume(self):
        r = parse_resume(TEXT, "2026-10-05")
        self.assertEqual(r["printed_date"], "2026-10-05")
        self.assertEqual(r["masi"], 17159.50)
        self.assertEqual(r["masi_daily_pct"], -0.83)
        self.assertEqual(r["central_actions_mad"], 126462241.92)
        self.assertEqual(r["volume_global_mad"], 129594380.72)
        self.assertGreater(r["advancers"] + r["decliners"], 30)

    def test_daily_change_cross_check(self):
        r = parse_resume(TEXT, "2026-10-05")
        ok_prev = {"masi": 17159.50 / (1 - 0.0083)}
        self.assertEqual(validate(dict(r), ok_prev), [])
        self.assertIn("daily_change_mismatch", validate(dict(r), {"masi": 17000.0}))

    def test_date_mismatch_detected(self):
        r = parse_resume(TEXT, "2026-10-06")
        self.assertIn("date_mismatch", validate(r, None))


if __name__ == "__main__":
    unittest.main()
