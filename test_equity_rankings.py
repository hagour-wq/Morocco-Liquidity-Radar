import unittest
from unittest.mock import patch
from datetime import date,timedelta
from rank_equities import evaluate_fundamental,evaluate_technical,issuer_facts
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
 def test_flagged_session_blocks_technical_score(self):
  d=date.today();rows=[]
  k=0
  while len(rows)<30:
   if d.weekday()<5:rows.append({"date":d.isoformat(),"close":100+len(rows)*0.1,"volume":1000,"status":"validated"})
   d-=timedelta(days=1)
  rows[3]["status"]="ohlc_incoherent"
  x=evaluate_technical("XYZ","Example",rows)
  self.assertEqual(x["status"],"FLAGGED_DATA_IN_WINDOW")
  self.assertNotIn("score",x)
 def test_recent_corporate_action_blocks_technical_score(self):
  d=date.today();rows=[]
  while len(rows)<60:
   if d.weekday()<5:rows.append({"date":d.isoformat(),"close":100,"volume":1000,"status":"validated"})
   d-=timedelta(days=1)
  rows[10]["status"]="corporate_action_suspected"
  x=evaluate_technical("XYZ","Example",rows)
  self.assertEqual(x["status"],"CORPORATE_ACTION_RECENT")
  self.assertNotIn("score",x)
 def test_stale_copy_is_excluded_and_suspended_stock_labelled(self):
  d=date.today();rows=[]
  while len(rows)<40:
   if d.weekday()<5:rows.append({"date":d.isoformat(),"close":100+len(rows)*0.1,"high":101+len(rows)*0.1,"low":99,"volume":1000,"turnover_mad":2e6,"status":"validated"})
   d-=timedelta(days=1)
  rows[5]["status"]="stale_copy_of_previous_session"
  x=evaluate_technical("XYZ","Example",rows)
  self.assertEqual(x["status"],"RESEARCH_ONLY")
  self.assertEqual(x["excluded_stale_dates"],[rows[5]["date"]])
  zero=[dict(r,close=0) for r in rows]
  self.assertEqual(evaluate_technical("XYZ","Example",zero)["status"],"NO_VALID_PRICES")
 def test_legal_market_closure_is_not_a_gap(self):
  d=date.today();rows=[]
  while len(rows)<40:
   if d.weekday()<5:rows.append({"date":d.isoformat(),"close":100+len(rows)*0.1,"volume":1000,"turnover_mad":2e6,"status":"validated"})
   d-=timedelta(days=1)
  rows.sort(key=lambda r:r["date"])
  closure=[r for r in rows if not (rows[20]["date"]<r["date"]<=(date.fromisoformat(rows[20]["date"])+timedelta(days=5)).isoformat())]
  self.assertEqual(evaluate_technical("XYZ","Example",closure)["status"],"RESEARCH_ONLY")
  long_gap=[r for r in rows if not (rows[20]["date"]<r["date"]<=(date.fromisoformat(rows[20]["date"])+timedelta(days=10)).isoformat())]
  self.assertEqual(evaluate_technical("XYZ","Example",long_gap)["status"],"GAPPED_HISTORY")
 def test_dividend_yield_only_when_recent(self):
  r={"isin":"MA0000012445","last_dividend_mad":22.0,"dividend_fiscal_year":2025,"dividend_ex_date":"2026-07-08"}
  self.assertEqual(issuer_facts(r,670.0,"2026-10-08")["dividend_yield_pct"],3.28)
  old=dict(r,dividend_ex_date="2023-08-23")
  self.assertIsNone(issuer_facts(old,670.0,"2026-10-08")["dividend_yield_pct"])
  self.assertIsNone(issuer_facts(dict(r,last_dividend_mad=None),670.0,"2026-10-08")["dividend_yield_pct"])
if __name__=="__main__":unittest.main()
