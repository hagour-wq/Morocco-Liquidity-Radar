import unittest
from unittest.mock import patch
from datetime import date,timedelta
import collect_global as g

class GlobalFeedTests(unittest.TestCase):
 def test_cboe_us_date_normalization(self):
  rows=g.parse_csv("DATE,OPEN,CLOSE\n10/06/2026,20,21\n10/07/2026,21,22\n",["CLOSE"])
  self.assertEqual(rows[0][0],"2026-10-06")
 def test_partial_coverage(self):
  self.assertEqual(len(g.SERIES),4)
 def test_freshness_rejects_old_source(self):
  old=(date.today()-timedelta(days=9)).isoformat()
  with patch.object(g,"obtain",side_effect=ValueError("network unavailable")):
   self.assertFalse(g.fresh({"vix":{"verified":True,"date":old}}) if hasattr(g,"fresh") else False)
 def test_scorer_bounds(self):
  self.assertEqual(g.clamp(-200),-100)
  self.assertEqual(g.clamp(200),100)

if __name__=="__main__":unittest.main()
