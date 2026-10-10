import unittest
from pathlib import Path
from extract_financials import social_equity_from_split_passif, _capital_increase_explains, split_two, extract, checks, parse_tail, unit_at, year_order_at, flatten, equity_from_variation, social_bank_equity, social_cost_of_risk, _social_like
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


class RobustnessTests(unittest.TestCase):
    """Cas réels relevés sur les comptes 2025 (SNEP, CMT, Addoha, Risma, Cartier Saada, Taqa, Aradei)."""
    def test_signs_dashes_and_decimal_points(self):
        self.assertEqual(parse_tail("- 185 186 -43 811")[:2], (-185186.0, -43811.0))           # SNP : perte
        self.assertEqual(parse_tail("1.13 0.68")[:2], (1.13, 0.68))                             # ADH : BPA à point décimal
        self.assertIsNone(parse_tail("124 211 405,73 - 123 837 936,73 102 403 753,01"))        # colonnes incohérentes : rien plutôt que faux
        self.assertEqual(parse_tail("105 777 740 75 299 358 61 709 782")[:2], (105777740.0, 75299358.0))

    def test_column_order_from_header(self):
        t = flatten("Compte de résultat consolidé\n2024 2025\nChiffre d'affaires 1 263 775 1 633 532\n")
        self.assertEqual(year_order_at(t, t.index("Chiffre")), "asc")
        f = extract("COMPTE DE RESULTAT CONSOLIDE (en milliers de MAD)\n2024 2025\nChiffre d'affaires 1 263 775 1 633 532\n"
                    "Résultat net part du groupe 183 024 269 622\n", "corporate")
        self.assertEqual((f["revenue"]["current"], f["net_income_group"]["current"]), (1633532.0, 269622.0))
        p = flatten("STE X Du 1/4/2025 Au 31/3/2026\nExercice Exercice Précédent\nVI = RESULTAT D'EXPLOITATION -13 821 353,73 16 946 033,61\n")
        self.assertEqual(year_order_at(p, p.index("VI =")), "desc")                      # une période n'est pas un en-tête de colonnes

    def test_unit_inferred_only_when_unique(self):
        txt = ("COMPTE DE RESULTAT CONSOLIDE\nChiffre d'affaires 2 708 923 803 2 594 688 796\nRésultat net - Part du groupe 453 719 263 274 184 241\n"
               "BILAN (en milliers de dirhams)\nCapitaux propres part du groupe 9 481 695 9 319 494\n")
        f = extract(txt, "corporate")
        self.assertIsNone(f["net_income_group"]["unit"])
        d, e, n = checks(f, "corporate", 402551254, 30.12)
        self.assertEqual(f["net_income_group"]["unit"], 1.0)                                  # ROE 4,8 % : seule unité plausible
        self.assertTrue(any("déduite" in x for x in n))
        self.assertAlmostEqual(d["roe_pct"], 100 * 453719263 / ((9481695e3 + 9319494e3) / 2), places=3)

    def test_group_share_without_label_requires_published_eps(self):
        base = ("COMPTE DE RESULTAT CONSOLIDE (en milliers de dirhams)\nChiffre d'affaires 11 931 188 7 596 821\n"
                "Résultat consolidé 952 053 521 810\nDont part du groupe 952 053 521 810\nCapitaux Propres Part Groupe 4 544 126 1 761 218\n")
        good = extract(base + "Résultat par action 27,5 16,5\n", "corporate")
        d, e, n = checks(good, "corporate", 34674332, 634.9)
        self.assertEqual(e, [])
        self.assertEqual(good["net_income_group"]["mad"], 952053e3)
        bad = extract(base, "corporate")                                                        # sans BPA : rejet
        d, e, n = checks(bad, "corporate", 34674332, 634.9)
        self.assertTrue(any("non confirmée par un BPA" in x for x in e))


class BalanceTotalTests(unittest.TestCase):
    def test_gross_minus_depreciation_layout(self):                      # bilan actif CGNC : brut, amortissements, net N, net N-1
        self.assertEqual(parse_tail("6 839 901 119,98 4 715 615 220,19 2 124 285 899,79 1 743 538 914,53")[:2], (2124285899.79, 1743538914.53))

    def test_total_assets_labels(self):
        f = extract("BILAN CONSOLIDE (en milliers de MAD)\nCapitaux propres part du groupe 788 101 720 476\nTOTAL DE L 'ACTIF 3 919 529 3 430 306\n"
                    "COMPTE DE RESULTAT\nChiffre d'affaires 3 251 072 2 940 457\nRésultat net part du groupe 112 330 57 886\n", "corporate")
        self.assertEqual(f["total_assets"]["mad"], 3919529e3)
        d, e, n = checks(f, "corporate", 1980000, 1225.0)
        self.assertAlmostEqual(d["equity_ratio_pct"], 100 * 788101 / 3919529, places=3)   # capitaux propres part du groupe à défaut du total


class BankRobustnessTests(unittest.TestCase):
    """CIH, CDM : graphiques du communiqué, unités dans le texte, minoritaires à néant, augmentation de capital."""
    def test_chart_axis_and_prose_units_ignored(self):
        txt = ("RNPG\n(en MDH)\n2024 2025\n875,9\n1 089,4\n+24,4 %\n"
               "représentent 1,6 milliards de dirhams pour une exigence de 130 millions de dirhams.\n"
               "COMPTE DE RESULTAT CONSOLIDE en Kdh\nPRODUIT NET BANCAIRE 5 422 526 4 739 507\n"
               "RESULTAT NET PART DU GROUPE 1 089 362 875 878\n")
        f = extract(txt, "bank")
        self.assertEqual(f["net_income_group"]["current"], 1089362.0)       # pas d'inversion par l'axe « 2024 2025 »
        self.assertEqual(f["net_income_group"]["unit"], 1e3)                # « en Kdh », pas « (en MDH) » ni la phrase

    def test_nil_minorities_and_capital_increase(self):
        txt = ("BILAN CONSOLIDE (En milliers de DH)\nCapitaux propres 8 203 010 7 878 853\nRéserves consolidées 2 551 543 2 273 030\n"
               "Part du groupe 2 551 543 2 273 030\nPart des minoritaires - -\nRésultat net de l'exercice 863 551 740 949\n"
               "Part du groupe 863 551 740 949\nPart des minoritaires - -\n"
               "COMPTE DE RÉSULTAT CONSOLIDÉ (En milliers de DH)\nPRODUIT NET BANCAIRE 3 568 401 3 303 182\n"
               "Coût du risque -383 113 -398 408\nCharges générales d'exploitation 1 359 551 1 345 385\n"
               "Résultat net part du groupe 863 551 740 949\nRésultat par action 79,36 68,09\n")
        f = extract(txt, "bank")
        self.assertEqual(f["minority_interests"]["current"], 0.0)
        d, e, n = checks(f, "bank", 11626499, 921.0)
        self.assertEqual(e, [])
        self.assertTrue(any("augmentation de capital probable" in x for x in n))   # BPA sur nombre moyen pondéré (rapport 1,07)
        self.assertAlmostEqual(d["equity_group_mad"], 8203010e3)


class InsuranceTests(unittest.TestCase):
    def test_ifrs17_insurer(self):
        txt = ("COMPTE DE RESULTAT CONSOLIDE (en milliers de dirhams)\nProduits des activités d'assurance 4.1  6.396.362  6.186.016\n"
               "Charges afférentes aux activités d'assurance 5.6 -5.605.173 -5.417.866\nRÉSUL TAT NET (PART DU GROUPE) 676.523 690.920\n"
               "BILAN (en milliers de dirhams)\nCAPITAUX PROPRES - PART DU GROUPE 6.062.749 5.729.361 5.346.604\nTOTAL ACTIF 24.385.015 22.252.831 21.096.397\n")
        f = extract(txt, "insurance")
        self.assertEqual(f["net_income_group"]["mad"], 676523e3)          # « RÉSUL TAT » recollé, groupes à point
        self.assertEqual(f["equity_group"]["mad"], 6062749e3)             # 3 colonnes : N, N-1 retraité, ouverture
        d, e, n = checks(f, "insurance", 5341874, 2955.0)
        self.assertEqual(e, [])
        self.assertAlmostEqual(d["insurance_expense_ratio_pct"], 100 * 5605173 / 6396362, places=4)
        x = evaluate_fundamental({"ticker": "SAH", "name": "Sanlam", "model": "insurance", "status": "VERIFIED", "period_end": "2025-12-31",
                                  "listing_exchange": "Casablanca Stock Exchange", "listing_country": "MA", "derived": d},
                                 price=2955.0, price_date="2026-10-09", dividend_yield=3.3, volatility=20, liquidity_tier="moyenne")
        self.assertEqual(x["category"], "ELIGIBLE")
        self.assertIsNotNone(x["components"]["quality"])


class LossTests(unittest.TestCase):
    def test_loss_gives_zero_earnings_valuation(self):
        base = {"ticker": "SNP", "name": "SNEP", "model": "corporate", "status": "VERIFIED", "period_end": "2025-12-31",
                "listing_exchange": "Casablanca Stock Exchange", "listing_country": "MA"}
        loss = evaluate_fundamental({**base, "derived": {"eps_current_shares_mad": -77.16, "book_value_per_share_mad": 202.9}}, price=289.0, price_date="2026-10-09")
        gain = evaluate_fundamental({**base, "derived": {"eps_current_shares_mad": 20.0, "book_value_per_share_mad": 202.9}}, price=289.0, price_date="2026-10-09")
        self.assertIsNone(loss["pe"])
        self.assertLess(loss["components"]["valuation"], gain["components"]["valuation"])


class VariationTableTests(unittest.TestCase):
    """CFG Bank, comptes consolidés 2025 : capitaux propres lus dans le tableau de variation (lignes réelles)."""
    TXT = ("  TABLEAU DE VARIATION DES CAPITAUX PROPRES CONSOLIDE (En milliers de DH)\n"
           "Capitaux propres au 31 décembre 2024 700.159    638.545    10.524    591.589   -127.897    1.812.920    27.144    1.840.062   \n"
           "Capitaux propres au 31 décembre 2025 700.159    645.289    -      849.400   -130.645    2.065.577    21.553    2.087.129   \n")

    def test_group_minorities_total_with_identity(self):
        ev = equity_from_variation(self.TXT)
        self.assertEqual((ev["equity_group"]["current"], ev["equity_group"]["previous"]), (2065577, 1812920))
        self.assertEqual(ev["minority_interests"]["current"], 21553)
        self.assertEqual(ev["equity_total"]["current"], 2087129)
        self.assertEqual(ev["equity_group"]["unit"], 1000)

    def test_rejected_when_identity_fails(self):
        bad = self.TXT.replace("2.087.129", "2.187.129")
        self.assertIsNone(equity_from_variation(bad))      # exercice courant incohérent : rien n'est retenu

    def test_needs_previous_year(self):
        one = "\n".join(l for l in self.TXT.splitlines() if "2024" not in l)
        self.assertIsNone(equity_from_variation(one))


class PcecTests(unittest.TestCase):
    """Établissements de crédit au format PCEC (lignes réelles Salafin, EQDOM 2025, en milliers de DH)."""
    PASSIF = ("en milliers de DH\n    PASSIF 31/12/2025 31/12/2024\n"
              "Provisions réglementées 17 673 19 798\nDettes subordonnées 0 0\n"
              "Réserves et primes liées au capital 462 304 461 319\nCapital 312 412 312 412\n"
              "Actionnaires. Capital non versé (-) 0 0\nReport à nouveau (+/-) 0 0\n"
              "Résultats nets en instance d'affectation (+/-) 0 0\nRésultat net de l'exercice (+/-) 96 117 93 147\n"
              "Total du Passif 3 813 381 3 726 279\n")
    CPC = ("DOTATIONS AUX PROVISIONS ET PERTES SUR CREANCES 323 327 85 296\nIRRECOUVRABLES\n"
           "REPRISES DE PROVISIONS ET RECUPERATIONS SUR 287 311 9 291\nCREANCES AMORTIES\n")

    def test_equity_is_sum_of_passif_items_checked_against_result(self):
        e = social_bank_equity(self.PASSIF, {"current": 96117, "previous": 93147})
        self.assertEqual((e["current"], e["previous"]), (870833, 866878))
        self.assertIsNone(social_bank_equity(self.PASSIF, {"current": 99999, "previous": 93147}))   # résultat discordant

    def test_cost_of_risk_is_net_of_reprises(self):
        c = social_cost_of_risk(self.CPC)
        self.assertEqual((c["current"], c["previous"]), (-36016, -76005))

    def test_variation_table_with_space_grouped_amounts_and_typo(self):
        t = ("Capitaux propores clôture au 31 décembre 2024  167 025    83 325    -      1 136 810    -      1 387 160      623          1 387 783   \n"
             "Capitaux propores clôture au 31 décembre 2025  167 025    83 325    -      1 235 372    -      1 485 722    717    1 486 439   \n")
        ev = equity_from_variation(t)
        self.assertEqual((ev["equity_group"]["current"], ev["minority_interests"]["current"], ev["equity_total"]["current"]), (1485722, 717, 1486439))
        self.assertEqual(ev["equity_group"]["previous"], 1387160)

    def test_roman_numbered_pcec_line_is_not_flagged_social(self):
        self.assertFalse(_social_like({"line": "IV. CHARGES GENERALES D'EXPLOITATION 356 638 325 628"}))
        self.assertTrue(_social_like({"line": "III = RESULTAT COURANT 1 234 1 111"}))


class RejectBatchTests(unittest.TestCase):
    """Corrections du lot « rejets » (lignes réelles des comptes 2025)."""
    def test_vertical_margin_letter_and_dash_prefix(self):
        self.assertEqual(parse_tail("59.914.634,13 55.159.969,69")[:2], (59914634.13, 55159969.69))
        t = extract("Résultat net de l'exercice (2) 59.914.634,13 55.159.969,69N\nT Total des capitaux propres        (A) 195 438 452,04 193 090 661,08\n", "corporate")
        self.assertEqual(t["net_income_group"]["current"], 59914634.13)
        self.assertEqual(t["equity_total"]["current"], 195438452.04)

    def test_cpc_line_with_empty_detail_columns(self):
        self.assertEqual(parse_tail("0,00 0,00 69 547 790,96 67 814 205,42")[:2], (69547790.96, 67814205.42))

    def test_three_columns_own_plus_previous_is_not_n_minus_1(self):
        r = parse_tail("979.733.874,82 0,00 979.733.874,82")
        self.assertFalse(r and r[1] == 0)            # jamais « N-1 = 0 »

    def test_spaced_letters_and_space_before_cents(self):
        f = flatten(" XIII  RÉSUL T A T NET ( XI - XII )  25 878 107 ,91 19 364 056,78")
        self.assertIn("RÉSULTAT NET", f)
        self.assertIn("25 878 107,91", f)

    def test_variation_table_total_first_order(self):
        t = ("SITUATION A LA CLOTURE DE L'EXERCICE 2024 3 500 767 138,79 91 020 189,77 3 409 746 949,02\n"
             "SITUATION A LA CLOTURE DE L'EXERCICE 2025 3 774 471 165,05 104 317 165,15 3 670 153 999,90\n")
        ev = equity_from_variation(t)
        self.assertEqual((ev["equity_group"]["current"], ev["minority_interests"]["current"], ev["equity_total"]["current"]),
                         (3670153999.90, 104317165.15, 3774471165.05))

    def test_capital_increase_explains_eps(self):
        fin = {"share_capital": {"current": 1200000, "previous": 300000}, "eps": {"current": 37, "previous": 39},
               "net_income_group": {"mad_previous": 589759e3}}
        self.assertTrue(_capital_increase_explains(fin, 37, 60e6, 1341942e3 / 37, 1341942e3))
        fin["eps"]["previous"] = 30                  # BPA N-1 non cohérent : refusé
        self.assertFalse(_capital_increase_explains(fin, 37, 60e6, 1341942e3 / 37, 1341942e3))

    def test_split_passif_equity_sum_and_result(self):
        t = ("BILAN - PASSIF\nExercice Exercice Précédent\n167 108 094,68 152 299 965,73\n52 650 000,00 52 650 000,00\n0,00 0,00\n"
             "2 606 640,90 2 606 640,90\n115 122 500,00 74 672 000,00\n5 265 000,00 5 265 000,00\n0,00 0,00\n17 106 324,83 11 369 808,27\n"
             "0,00 0,00\n-25 642 371,05 5 736 516,56\n167 108 094,68 152 299 965,73\nTOTAL DES CAPITAUX PROPRES ( a )\n")
        e = social_equity_from_split_passif(t, {"current": -25642371.05, "previous": 5736516.56})
        self.assertEqual((e["current"], e["previous"]), (167108094.68, 152299965.73))
        self.assertIsNone(social_equity_from_split_passif(t, {"current": -25642371.05, "previous": 1.0}))


class CapitalUnitRescueTests(unittest.TestCase):
    def test_unit_from_published_share_capital(self):
        from collect_fundamentals import capital_unit_rescue
        fin = {"share_capital": {"current": 46595.40, "previous": 46595.40, "unit": 1.0},
               "equity_group": {"current": 262142.60, "previous": 247790.33, "unit": 1.0}}
        out, note = capital_unit_rescue("Société Anonyme au capital de 46.595.400 Dirhams - R.C.Tanger", fin)
        self.assertEqual(out["equity_group"]["mad"], 262142600.0)
        self.assertIn("capital social publié", note)
        self.assertIsNone(capital_unit_rescue("au capital de 50.000.000 Dirhams", fin))   # aucun rapport exact 1 / 1 000 / 1 000 000 : rien


class NoMinorityTests(unittest.TestCase):
    def test_total_equity_is_group_when_consolidated_result_equals_group_share(self):
        f = lambda c, p: {"current": c, "previous": p, "unit": 1000.0, "mad": c * 1e3, "mad_previous": p * 1e3, "line": "", "layout": "N / N-1"}
        fin = {"net_income_group": f(15447, 12428), "net_income": f(15447, 12428), "equity_total": f(319225, 307028),
               "revenue": f(330365, 311411), "_scope": "consolidated"}
        d, e, n = checks(fin, "corporate", None)
        self.assertEqual(e, [])
        self.assertEqual(d["equity_group_mad"], 319225e3)
        fin["net_income"] = f(16000, 12428)            # minoritaires au résultat : pas de déduction
        self.assertIn("capitaux propres part du groupe introuvables", checks(fin, "corporate", None)[1])


if __name__ == "__main__":
    unittest.main()
