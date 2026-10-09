import unittest
from pathlib import Path
from extract_financials import split_two, extract, checks
from rank_equities import evaluate_fundamental

FX = Path("tests/fixtures")
SHARES = {"ATW": 215140839, "BCP": 203312473, "MSA": 73395600, "MNG": 118646760}


def load(name, model):
    return extract((FX / name).read_text(encoding="utf-8"), model)


class SplitTests(unittest.TestCase):
    def test_glued_amounts_split_by_consistency(self):
        self.assertEqual(split_two("1 117 724 821 216")[:2], (1117724.0, 821216.0))
        self.assertEqual(split_two("795 461 302 726 492 948")[:2], (795461302.0, 726492948.0))
        self.assertEqual(split_two("13 693,6 8 859,4")[:2], (13693.6, 8859.4))
        self.assertEqual(split_two("-3 664 557 -4 210 257")[:2], (-3664557.0, -4210257.0))


class ExtractionTests(unittest.TestCase):
    def test_atw_bank_statements(self):
        f = load("comptes_ATW_awb_2025.txt", "bank")
        self.assertEqual(f["pnb"]["mad"], 34921384e3)
        self.assertEqual(f["net_income_group"]["mad"], 10644852e3)
        self.assertEqual(f["eps"]["mad"], 49.48)
        self.assertEqual(f["minority_interests"]["mad"], 11059101e3)   # = tableau de variation des capitaux propres
        d, e, n = checks(f, "bank", SHARES["ATW"])
        self.assertEqual(e, [])
        self.assertAlmostEqual(d["equity_group_mad"], 69431269e3)
        self.assertAlmostEqual(d["cost_income_pct"], 100 * (11799244 + 1423329) / 34921384, places=6)

    def test_bcp_minorities_from_three_lines(self):
        f = load("comptes_BCP_bcp_2025_0.txt", "bank")
        self.assertEqual(f["minority_interests"]["mad"], (20246892 - 383576 + 1117724) * 1e3)
        self.assertEqual(checks(f, "bank", SHARES["BCP"])[1], [])

    def test_msa_corporate_thousands(self):
        f = load("comptes_MSA_marsa_2025.txt", "corporate")
        self.assertEqual(f["revenue"]["mad"], 5784894e3)
        self.assertEqual(f["net_income_group"]["mad"], 1588764e3)
        d, e, n = checks(f, "corporate", SHARES["MSA"])
        self.assertEqual(e, [])
        self.assertAlmostEqual(d["equity_ratio_pct"], 100 * 4599248 / 9332718, places=4)

    def test_mng_millions_and_split_detected_from_eps(self):
        f = load("comptes_MNG_managem_2025.txt", "corporate")
        self.assertEqual(f["net_income_group"]["mad"], 3002.0e6)
        d, e, n = checks(f, "corporate", SHARES["MNG"])
        self.assertEqual(e, [])
        self.assertTrue(any("facteur 10" in x for x in n))
        self.assertAlmostEqual(d["eps_current_shares_mad"], 3002.0e6 / SHARES["MNG"])

    def test_inconsistent_eps_is_rejected(self):
        f = load("comptes_BCP_bcp_2025_0.txt", "bank")
        self.assertTrue(checks(f, "bank", 150_000_000)[1])


class ScoreTests(unittest.TestCase):
    def company(self, **kw):
        c = {"ticker": "ATW", "model": "bank", "fiscal_year": 2025, "period_end": "2025-12-31", "status": "VERIFIED",
             "listing_exchange": "Casablanca Stock Exchange", "listing_country": "MA",
             "derived": {"eps_current_shares_mad": 49.48, "book_value_per_share_mad": 322.7, "roe_pct": 16.1, "cost_income_pct": 37.9,
                         "pnb_growth_pct": 1.2, "net_income_growth_pct": 12.0, "cost_of_risk_to_loans_pct": 0.82}}
        c.update(kw)
        return c

    def test_bank_scored_and_eligible(self):
        x = evaluate_fundamental(self.company(), 670.0, "2026-10-08", 3.28, 13.7, "élevée")
        self.assertEqual(x["category"], "ELIGIBLE")
        self.assertEqual(x["pe"], round(670 / 49.48, 2))
        self.assertTrue(0 <= x["score"] <= 100)
        self.assertEqual(x["risk_level"], "faible")

    def test_missing_component_gives_partial_watch(self):
        x = evaluate_fundamental(self.company(), 670.0, "2026-10-08", None, 13.7, "élevée")
        self.assertEqual(x["category"], "WATCH")
        self.assertIn("dividend", x["missing_components"])

    def test_stale_accounts_and_unreadable_document_excluded(self):
        self.assertEqual(evaluate_fundamental(self.company(period_end="2024-12-31"), 670.0, "2026-10-08", 3.0)["status"], "STALE_OR_UNDATED")
        x = evaluate_fundamental(self.company(status="UNREADABLE", reason="PDF image"), 670.0, "2026-10-08")
        self.assertEqual((x["category"], x["status"]), ("NON_ANALYSABLE", "UNREADABLE"))

    def test_unverified_listing_not_ranked(self):
        x = evaluate_fundamental(self.company(listing_exchange=None), 670.0, "2026-10-08", 3.0)
        self.assertEqual(x["status"], "EXCHANGE_NOT_VERIFIED")
        self.assertNotIn("score", x)


if __name__ == "__main__":
    unittest.main()
