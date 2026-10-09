import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import equity_store as store


class StoreTests(unittest.TestCase):
    def test_roundtrip_one_session_per_line(self):
        with tempfile.TemporaryDirectory() as t, patch.object(store, "DIR", Path(t)):
            c = {"ticker": "ATW", "name": "ATTIJARIWAFA BANK", "sector": "Banques",
                 "rows": [{"date": "2026-10-07", "close": 668.0}, {"date": "2026-10-08", "close": 670.0}]}
            store.save(c)
            text = store.path("ATW").read_text(encoding="utf-8")
            self.assertEqual(json.loads(text), c)
            self.assertEqual(sum(1 for line in text.splitlines() if line.startswith('{"date"')), 2)
            store.save_index(store.load_all(), "now")
            idx = json.loads((Path(t) / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(idx["companies"][0]["sessions"], 2)
            self.assertEqual(len(store.load_all()), 1)


if __name__ == "__main__":
    unittest.main()
