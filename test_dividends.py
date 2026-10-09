"""Calendrier financier officiel (extrait réel de la page /emetteurs/calendrier-financier du 10/10/2026)."""
import json, unittest
from pathlib import Path
import collect_dividends as cd
from rank_equities import issuer_facts

FX = json.loads(Path("tests/fixtures/calendrier_financier_extrait.json").read_text(encoding="utf-8"))
NAMES = {cd.norm("ATTIJARIWAFA BANK"): "ATW", cd.norm("MANAGEM"): "MNG", cd.norm("CREDIT DU MAROC"): "CDM",
         cd.norm("BANK OF AFRICA"): "BOA", cd.norm("ARADEI CAPITAL"): "ARD"}


class ParseTests(unittest.TestCase):
    def setUp(self):
        self.by, self.unmatched, self.issues = cd.parse(FX, NAMES)

    def test_amounts_dates_and_order(self):
        atw = self.by["ATW"]["dividends"]
        self.assertEqual((atw[0]["ex_date"], atw[0]["payment_date"], atw[0]["amount_mad"]), ("2026-07-08", "2026-07-17", 22.0))
        self.assertEqual([d["ex_date"] for d in atw], sorted((d["ex_date"] for d in atw), reverse=True))
        self.assertTrue(self.by["ATW"]["meetings"])

    def test_zero_amount_rows_are_rejected_not_kept(self):
        self.assertTrue(any(i["emetteur"] == "BANK OF AFRICA" and i["published"] == "0,00 MAD" for i in self.issues))
        self.assertFalse(any(d["amount_mad"] == 0 for v in self.by.values() for d in v["dividends"]))

    def test_unknown_issuer_kept_apart(self):
        by, unmatched, _ = cd.parse(FX, {k: v for k, v in NAMES.items() if v != "CDM"})
        self.assertIn("CREDIT DU MAROC", unmatched)
        self.assertNotIn("CDM", by)

    def test_bulletin_cross_check_detects_split_adjustment(self):
        ref = {"MNG": {"dividend_ex_date": "2026-07-15", "last_dividend_mad": 5.5},
               "ATW": {"dividend_ex_date": "2026-07-08", "last_dividend_mad": 22.0},
               "XYZ": {"dividend_ex_date": "2011-09-21", "last_dividend_mad": 18.0}}
        c = cd.cross_check(self.by, ref)
        self.assertIn("MNG", c)              # 55 MAD au calendrier, 5,5 MAD ajusté au bulletin (division par 10 le 27/07/2026)
        self.assertNotIn("ATW", c)
        self.assertNotIn("XYZ", c)           # antérieur à la couverture du calendrier


class YieldTests(unittest.TestCase):
    def setUp(self):
        self.by, _, _ = cd.parse(FX, NAMES)

    def test_trailing_twelve_months_ordinary(self):
        x = issuer_facts({"isin": "MA0000012445"}, 670.0, "2026-10-09", self.by["ATW"]["dividends"])
        self.assertEqual(x["dividend_yield_pct"], round(100 * 22 / 670, 2))
        self.assertIn("calendrier officiel", x["dividend_yield_basis"])

    def test_dividend_before_split_uses_adjusted_bulletin_amount(self):
        r = {"dividend_ex_date": "2026-07-15", "last_dividend_mad": 5.5}
        x = issuer_facts(r, 1479.0, "2026-10-09", self.by["MNG"]["dividends"], ca_dates=["2026-07-27"])
        self.assertEqual(x["dividend_yield_pct"], round(100 * 5.5 / 1479, 2))   # et non 55 / 1 479 = 3,7 %
        self.assertTrue(x["dividend_notes"])
        y = issuer_facts({}, 1479.0, "2026-10-09", self.by["MNG"]["dividends"], ca_dates=["2026-07-27"])
        self.assertIsNone(y["dividend_yield_pct"])                                 # montant ajusté inconnu : écarté

    def test_exceptional_dividend_excluded_from_yield(self):
        x = issuer_facts({}, 425.2, "2026-10-09", self.by["ARD"]["dividends"])
        self.assertEqual(x["exceptional_dividends_12m_mad"], 17.29)
        self.assertNotEqual(x["dividend_yield_pct"], round(100 * 17.29 / 425.2, 2))


if __name__ == "__main__":
    unittest.main()
