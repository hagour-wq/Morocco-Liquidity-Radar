import unittest
from unittest.mock import patch
from datetime import date,timedelta
from rank_equities import evaluate_fundamental,evaluate_technical
class EquityRankingTests(unittest.TestCase):
 def test_unverified_listing_is_not_ranked(self):
  x=evaluate_fundamental({"ticker":"XYZ","name":"Example"})
  self.assertEqual(x["status"],"EXCHANGE_NOT_VERIFIED")
  self.assertNotIn("score",x)
 def test_missing_fundamental_is_not_ranked(self):
  x=evaluate_fundamental({"ticker":"XYZ","name":"Example","listing_exchange":"Casablanca Stock Exchange","listing_country":"MA"})
  self.assertEqual(x["status"],"INSUFFICIENT_DATA")
  self.assertIn("eps_mad",x["missing_fields"])
  self.assertNotIn("score",x)
 def test_sparse_price_history_is_not_ranked(self):
  x=evaluate_technical("XYZ","Example",[{"date":"2026-10-07","close":100,"volume":200}])
  self.assertEqual(x["status"],"INSUFFICIENT_HISTORY")
 def test_verified_fundamentals_are_ranked_only_when_complete(self):
  x={"ticker":"XYZ","name":"Test issuer","reference_date":date.today().isoformat(),"source_url":"https://example.org/report.pdf","listing_exchange":"Casablanca Stock Exchange","listing_country":"MA","price_mad":100,"eps_mad":8,"book_value_per_share_mad":50,"roe_pct":16,"revenue_growth_pct":7,"net_debt_ebitda":1.5,"dividend_per_share_mad":4}
  result=evaluate_fundamental(x)
  self.assertEqual(result["status"],"RESEARCH_ONLY")
  self.assertTrue(0<=result["score"]<=100)
 def test_stale_report_is_rejected(self):
  x={"ticker":"XYZ","name":"Test issuer","reference_date":"2020-01-01","source_url":"https://example.org/old.pdf","listing_exchange":"Casablanca Stock Exchange","listing_country":"MA","price_mad":100,"eps_mad":8,"book_value_per_share_mad":50,"roe_pct":16,"revenue_growth_pct":7,"net_debt_ebitda":1.5,"dividend_per_share_mad":4}
  self.assertNotIn("score",evaluate_fundamental(x))
if __name__=="__main__":unittest.main()
