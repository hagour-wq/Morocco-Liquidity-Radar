import json,tempfile,unittest
from pathlib import Path
from backtest import sync_dashboard
class BacktestSyncTests(unittest.TestCase):
 def test_dashboard_block_mirrors_backtest_output(self):
  with tempfile.TemporaryDirectory() as t:
   dash=Path(t)/"dashboard.json"
   dash.write_text(json.dumps({"backtest":{"usable_5d":18,"directional_accuracy_5d_pct":61.1},"composite":5}),encoding="utf-8")
   sync_dashboard({"history_sessions":87,"observations":82,"usable_5d":47,"directional_accuracy_5d_pct":48.9},dash)
   d=json.loads(dash.read_text(encoding="utf-8"))
   self.assertEqual(d["backtest"]["usable_5d"],47)
   self.assertEqual(d["backtest"]["directional_accuracy_5d_pct"],48.9)
   self.assertIn("non concluant",d["backtest"]["warning"])
   self.assertEqual(d["composite"],5)
if __name__=="__main__":unittest.main()
