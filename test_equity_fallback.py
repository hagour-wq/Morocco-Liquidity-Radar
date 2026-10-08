import unittest
from unittest.mock import patch
from datetime import date,datetime,timezone,timedelta
import backfill_equities_fallback as f
class FallbackTests(unittest.TestCase):
 def test_reject_wrong_market_even_if_symbol_ends_cs(self):
  bad={"chart":{"result":[{"meta":{"exchangeName":"NYSE","currency":"USD"},"timestamp":[],"indicators":{"quote":[{}]}}]}}
  with patch.object(f,"urlopen") as op:
   op.return_value.__enter__.return_value.read.return_value=__import__("json").dumps(bad).encode()
   with self.assertRaisesRegex(ValueError,"unverified_exchange_currency"):f.history("BCP")
 def test_discover_existing_rotation(self):
  tickers=f.candidates()
  self.assertIsInstance(tickers,dict)
  for key in tickers:self.assertTrue(key.isalnum())
if __name__=="__main__":unittest.main()
