import unittest
from unittest.mock import patch
import backfill_equities as b
class BackfillTests(unittest.TestCase):
 def test_extract_official_json_api_structure(self):
  payload={"data":[{"type":"instrument_history","id":"1","attributes":{"created":"2026-09-30T16:00:00Z","closingPrice":"251,50","cumulTitresEchanges":"1290"},"relationships":{"symbol":{"data":{"type":"instrument","id":"abc"}}}}],"included":[{"type":"instrument","id":"abc","attributes":{"symbol":"BCP","libelleFR":"BCP"}}]}
  rows=b.normalized(payload)
  self.assertEqual(len(rows),1)
  self.assertEqual(rows[0]["ticker"],"BCP")
  self.assertEqual(rows[0]["row"]["close"],251.5)
  self.assertEqual(rows[0]["row"]["volume"],1290)
 def test_discard_unknown_symbol(self):
  payload={"data":[{"id":"1","attributes":{"created":"2026-09-30","closingPrice":251.5,"cumulTitresEchanges":100},"relationships":{}}],"included":[]}
  self.assertEqual(b.normalized(payload),[])
 def test_missing_volume_never_fabricated(self):
  payload={"data":[{"id":"1","attributes":{"created":"2026-09-30","closingPrice":251.5},"relationships":{"symbol":{"data":{"id":"abc"}}}}],"included":[{"id":"abc","attributes":{"symbol":"BCP"}}]}
  self.assertEqual(b.normalized(payload),[])
if __name__=="__main__":unittest.main()
