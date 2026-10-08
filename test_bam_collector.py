import unittest
from collect_bam import extract_monthly
class TestDEPF(unittest.TestCase):
 def test_august(self):
  text="besoins des banques se situant en moyenne hebdomadaire à 132,3 milliards de dirhams après 125,7 milliards en juillet. La Banque Centrale a augmenté le volume de ses injections de liquidité qui s’est établi en moyenne hebdomadaire à 150 milliards de dirhams après 144,1 milliards en juillet."
  x=extract_monthly(text)
  self.assertIsNotNone(x)
  self.assertEqual(x["liquidity_need_current_bn_mad"],132.3)
  self.assertEqual(x["injections_previous_bn_mad"],144.1)
 def test_july_comma(self):
  text="besoins des banques se situant en moyenne hebdomadaire à 125,7 milliards de dirhams après 127,3 milliards en juin. La Banque Centrale a réduit le volume de ses injections de liquidité qui s’est établi en moyenne hebdomadaire à 144,1 milliards de dirhams, après 152,4 milliards en juin."
  x=extract_monthly(text)
  self.assertIsNotNone(x)
  self.assertEqual(x["injections_current_bn_mad"],144.1)
if __name__=="__main__":unittest.main()
