import unittest
from backfill_equities_public import parse_table,number,volume
class ArchiveTests(unittest.TestCase):
 def test_french_market_table(self):
  html='<table><tr><th>Date</th><th>Dernier</th><th>Ouv.</th><th>Plus Haut</th><th>Plus Bas</th><th>Vol.</th></tr><tr><td>07/10/2026</td><td>673,20</td><td>680,00</td><td>680,00</td><td>670,00</td><td>90,82K</td></tr></table>'
  rows=parse_table(html)
  self.assertEqual(len(rows),1)
  self.assertEqual(rows[0]['close'],673.2)
  self.assertAlmostEqual(rows[0]['volume'],90820)
 def test_unrelated_table_does_not_parse(self):
  self.assertEqual(parse_table('<table><tr><td>not a session</td><td>100</td><td>x</td><td>x</td><td>x</td><td>2K</td></tr></table>'),[])
if __name__=='__main__':unittest.main()
