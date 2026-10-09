import unittest
from datetime import date
from unittest.mock import patch
import casablanca_source as cb
from collect_equities import to_row, validate_row, split_factor

ITEM = {"seance": "08/10/2026", "ouverture": 680, "dernierCours": 670, "plusHaut": 680, "plusBas": 670,
        "titresEchanges": 49319, "volumeEchanges": 33070916.7, "nbTransactions": 113, "capitalisation": 144144362130}


class SourceTests(unittest.TestCase):
    def test_tls_context_loads_bundled_intermediate(self):
        self.assertTrue(cb.INTERMEDIATE.exists())
        self.assertGreater(len(cb.tls_context().get_ca_certs()), 50)

    def test_parse_seance_is_day_first(self):
        self.assertEqual(cb.parse_seance("01/10/2025"), date(2025, 10, 1))

    def test_stock_history_windows_and_stops_on_empty(self):
        calls = []
        def fake(path, params):
            calls.append((params["startDate"], params["endDate"]))
            if len(calls) == 1:
                return {"totalCount": 2, "items": [ITEM, dict(ITEM, seance="07/10/2026")]}
            return {"totalCount": 0, "items": []}
        with patch.object(cb, "get_json", side_effect=fake):
            rows = cb.stock_history("ATW", date(2020, 1, 1), date(2026, 10, 9))
        self.assertEqual([cb.parse_seance(r["seance"]).isoformat() for r in rows], ["2026-10-07", "2026-10-08"])
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][1], "2026-10-09")

    def test_stock_history_refuses_silent_truncation(self):
        with patch.object(cb, "get_json", return_value={"totalCount": 5000, "items": [ITEM]}):
            with self.assertRaises(ValueError):
                cb.stock_history("ATW", date(2026, 1, 1), date(2026, 10, 9))

    def test_index_history_handles_ms_and_casablanca_date(self):
        # 2026-10-07T23:00Z = 8 octobre 00:00 à Casablanca (UTC+1)
        with patch.object(cb, "get_json", return_value={"items": [{"time": 1791414000000, "close": 16990.77}]}):
            rows, _ = cb.index_history()
        self.assertEqual(rows[0]["date"], "2026-10-08")
        self.assertEqual(rows[0]["close"], 16990.77)


class EquityRowTests(unittest.TestCase):
    def test_row_keeps_shares_and_mad_turnover_distinct(self):
        r = to_row(ITEM, "now")
        self.assertEqual((r["date"], r["close"], r["volume"], r["turnover_mad"]), ("2026-10-08", 670, 49319, 33070916.7))
        self.assertIsNone(r["adj_close"])

    def test_validation_flags(self):
        r = to_row(ITEM, "now")
        self.assertEqual(validate_row(r, 668), [])
        self.assertIn("ohlc_incoherent", validate_row(dict(r, close=700), 668))
        self.assertIn("move_gt_10pct", validate_row(r, 500))
        self.assertIn("weekend_date", validate_row(dict(r, date="2026-10-10"), 668))
        self.assertIn("close_non_positive", validate_row(dict(r, close=0), 668))


class VolumeSemanticsTests(unittest.TestCase):
    def test_incomplete_record_is_missing_not_zero(self):
        r = to_row(dict(ITEM, ouverture=None, titresEchanges=0, volumeEchanges=0, nbTransactions=0), "now")
        self.assertIsNone(r["volume"])
        self.assertIsNone(r["turnover_mad"])
        self.assertTrue(r["incomplete_volume"])
        self.assertIn("incomplete_volume", validate_row(r, 668))

    def test_no_trade_session_is_zero(self):
        r = to_row({"seance": "08/10/2026", "dernierCours": 1599, "titresEchanges": None}, "now")
        self.assertEqual(r["volume"], 0.0)
        self.assertIs(r["traded"], False)


class CorporateActionTests(unittest.TestCase):
    def test_managem_like_split_is_detected(self):
        self.assertEqual(split_factor(12500, {"open": 1340}), 9)
        self.assertEqual(split_factor(12500, {"open": 1250}), 10)

    def test_ordinary_limit_move_is_not_a_split(self):
        self.assertIsNone(split_factor(100, {"open": 89}))
        self.assertIsNone(split_factor(100, {"open": 111}))


if __name__ == "__main__":
    unittest.main()
