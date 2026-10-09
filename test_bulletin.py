import unittest
from pathlib import Path
from collect_bulletin import parse_bulletin, match

TEXT = Path("tests/fixtures/bulletin_extrait_20261005.txt").read_text(encoding="utf-8")


class BulletinTests(unittest.TestCase):
    def setUp(self):
        self.recs = {r["isin"]: r for r in parse_bulletin(TEXT)}

    def test_equity_lines_parsed_bonds_and_rights_ignored(self):
        self.assertIn("MA0000012445", self.recs)              # ATW
        self.assertNotIn("MA0000801185", self.recs)           # droit d'attribution BOA
        self.assertFalse(any(r["isin"].startswith("MA00000217") for r in self.recs.values()))  # obligations

    def test_atw_fields(self):
        r = self.recs["MA0000012445"]
        self.assertEqual((r["shares"], r["nominal_mad"], r["sector_code"]), (215140839, 10.0, "BAN"))
        self.assertEqual((r["last_dividend_mad"], r["dividend_fiscal_year"], r["dividend_ex_date"]), (22.0, 2025, "2026-07-08"))
        self.assertEqual(r["reference_price_mad"], 675.0)

    def test_shares_nominal_split_and_missing_dividend(self):
        self.assertEqual(self.recs["MA0000011488"]["shares"], 879095340)       # IAM, nominal 6
        self.assertEqual(self.recs["MA0000011488"]["nominal_mad"], 6.0)
        mp = self.recs["MA0000012593"]                                          # MED PAPER : exercice sans dividende
        self.assertIsNone(mp["last_dividend_mad"])
        self.assertEqual(mp["dividend_fiscal_year"], 2009)

    def test_match_by_exact_share_count(self):
        live = {"ATW": {"nombreTitres": 215140839, "reference": 675}, "XXX": {"nombreTitres": 1}}
        m, un = match(list(self.recs.values()), live)
        self.assertEqual(m["ATW"]["isin"], "MA0000012445")
        self.assertEqual(m["ATW"]["price_check"], "ok")


class TieBreakTests(unittest.TestCase):
    def test_same_share_count_resolved_by_price(self):
        recs = [{"isin": "A", "name_bulletin": "AFMA", "shares": 1000000, "reference_price_mad": 1265.0},
                {"isin": "B", "name_bulletin": "PROMOPHARM", "shares": 1000000, "reference_price_mad": 2100.0}]
        live = {"AFM": {"nombreTitres": 1000000, "reference": 1265}, "PRO": {"nombreTitres": 1000000, "reference": 2105}}
        m, un = match(recs, live)
        self.assertEqual((m["AFM"]["isin"], m["PRO"]["isin"]), ("A", "B"))
        self.assertEqual(un, [])


if __name__ == "__main__":
    unittest.main()
