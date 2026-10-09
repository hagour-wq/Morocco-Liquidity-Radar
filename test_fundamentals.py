import unittest
from pathlib import Path
from extract_financials import split_two, extract, checks, parse_tail, unit_at
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


class LayoutTests(unittest.TestCase):
    """Dispositions de colonnes relevées dans les publications 2025 (lignes réelles)."""
    def test_variation_pct_checks_column_order(self):
        # LBV : N-1 puis N, ordre établi par la variation publiée
        self.assertEqual(parse_tail("16 418 18 534 +12,9%")[:2], (18534.0, 16418.0))
        # TQM : N, N-1, écart, %
        self.assertEqual(parse_tail("10 638 10 878 -240 -2,2%")[:3], (10638.0, 10878.0, "N / N-1 / écart / variation %"))
        # HPS : consolidé puis social sur la même ligne -> premier bloc
        self.assertEqual(parse_tail("106 75 +40,5% 106 62 +71,4%")[:2], (106.0, 75.0))

    def test_moroccan_cpc_four_columns(self):
        r = parse_tail("392 680 231,00 886 668,58 393 566 899,58 286 037 895,90")
        self.assertEqual(r[:2], (393566899.58, 286037895.90))
        self.assertTrue(r[2].startswith("CPC"))
        self.assertEqual(parse_tail("68.072.285,78 - 68.072.285,78 68.253.995,17")[:2], (68072285.78, 68253995.17))
        self.assertEqual(parse_tail("745 691 524,57 745 691 524,57 633 333 207,77")[:2], (745691524.57, 633333207.77))

    def test_dotted_thousands_and_parenthesised_negative(self):
        self.assertEqual(parse_tail("2.431.512 2.363.364")[:2], (2431512.0, 2363364.0))
        self.assertEqual(parse_tail("196 465 103 (12 125 978)")[:2], (196465103.0, -12125978.0))

    def test_units(self):
        txt = "BILAN (En millions de dirhams) 31-déc.-25 31-déc.-24\nRésultat par action (en dirhams) 41,58 44,63\n"
        self.assertEqual(unit_at(txt, len(txt)), 1e6)          # la ligne BPA chiffrée n'est pas un en-tête
        self.assertEqual(unit_at("(Montants en dhs) 31/12/2025 31/12/2024\n", 45), 1.0)
        self.assertEqual(unit_at("(En milliers MAD)\n", 18, "3 670 153 999,90 3 409 746 949,01"), 1.0)  # centimes : dirhams


SOCIAL_TXT = """BILAN (en dirhams)
Total des capitaux propres (A) 359 119 876,03 335 546 322,65
COMPTE DE PRODUITS ET CHARGES
Chiffres d'affaires 624 013 253,82 624 013 253,82 605 017 873,46
RESULTAT D'EXPLOITATION (I-II) 112 057 974,81 112 057 974,81 93 174 163,54
Résultat net de l'exercice (2) 65 479 341,98 45 337 135,25
"""
GROUP_SPLIT_TXT = """COMPTE DE RESULTAT CONSOLIDE (Montants en dhs) 31/12/2025 31/12/2024
Chiffre d'affaires 4 413 384 274 2 954 038 793
Résultat net de l'ensemble consolidé 494 331 591 347 553 992
Résultat de l'exercice 443 680 156 314 609 432
Intérêts minoritaires 50 651 435 32 944 560
BILAN PASSIF (Montants en dhs) 31/12/2025 31/12/2024
Capitaux propres de l'ensemble consolidé 2 925 562 585 2 638 508 203
Dont : Capitaux propres part du groupe 2 853 529 135 2 583 560 166
Chiffre d'affaires 999 999 999,00 888 888 888,00
"""


class ScopeTests(unittest.TestCase):
    def test_social_accounts_when_no_consolidated_statements(self):
        f = extract(SOCIAL_TXT, "corporate")
        self.assertEqual(f["_scope"], "social")
        self.assertEqual(f["net_income_group"]["mad"], 65479341.98)
        d, e, n = checks(f, "corporate", 16117611, 77.0)
        self.assertEqual(e, [])
        self.assertEqual(d["scope"], "social")
        self.assertAlmostEqual(d["revenue_growth_pct"], 100 * (624013253.82 / 605017873.46 - 1))

    def test_group_share_derived_by_arithmetic_and_social_lines_ignored(self):
        f = extract(GROUP_SPLIT_TXT, "corporate")
        self.assertEqual(f["_scope"], "consolidated")
        self.assertEqual(f["net_income_group"]["mad"], 443680156.0)      # 494 331 591 − 50 651 435
        self.assertIn("somme vérifiée", f["net_income_group"]["method"])
        self.assertEqual(f["revenue"]["mad"], 4413384274.0)             # jamais la ligne sociale à centimes
        self.assertEqual(f["equity_group"]["mad"], 2853529135.0)

    def test_unit_error_caught_by_implied_per(self):
        f = extract(GROUP_SPLIT_TXT, "corporate")
        f["net_income_group"]["mad"] *= 1000                             # erreur d'unité simulée
        d, e, n = checks(f, "corporate", 14159207, 1015.0)
        self.assertTrue(any("PER implicite" in x for x in e))


if __name__ == "__main__":
    unittest.main()
