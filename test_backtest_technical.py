import math, unittest
from datetime import date, timedelta
import backtest_technical as bt
from rank_equities import evaluate_technical


def rows(n, start=date(2026, 1, 5), f=lambda i: 100 + i):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            i = len(out)
            out.append({"date": d.isoformat(), "close": f(i), "high": f(i) + 1, "low": f(i) - 1, "volume": 1000,
                        "turnover_mad": 2e6, "traded": True, "status": "validated"})
        d += timedelta(days=1)
    return out


class NoLookAheadTests(unittest.TestCase):
    def test_score_ignores_sessions_after_as_of(self):
        r = rows(80)
        as_of = date.fromisoformat(r[49]["date"])
        past = evaluate_technical("X", "X", r[:50], as_of=as_of)
        crash = r[:50] + [dict(x, close=1.0, high=1.5, low=0.5) for x in r[50:]]  # futur radicalement différent
        self.assertEqual(evaluate_technical("X", "X", crash, as_of=as_of), past)
        self.assertEqual(past["reference_date"], r[49]["date"])


class MetricTests(unittest.TestCase):
    def test_stats_on_known_series(self):
        s = bt.stats([0.10, -0.10, 0.10, -0.10], years=1.0)
        self.assertAlmostEqual(s["total_return_pct"], 100 * (1.1 * 0.9 * 1.1 * 0.9 - 1), places=2)
        self.assertAlmostEqual(s["max_drawdown_pct"], 100 * (0.9801 / 1.1 - 1), places=1)  # pic 1,10 → creux 0,9801
        vol = math.sqrt(sum((x - 0) ** 2 for x in [0.1, -0.1, 0.1, -0.1]) / 3) * math.sqrt(4)
        self.assertAlmostEqual(s["annualized_volatility_pct"], round(100 * vol, 2), places=2)

    def test_holding_across_corporate_action_is_excluded(self):
        prices = {"MNG": ([("2026-07-24", 12500.0, 1), ("2026-07-27", 1364.0, 1), ("2026-07-28", 1315.0, 1)], {"2026-07-27"})}
        self.assertIsNone(bt.period_return(prices, "MNG", "2026-07-24", "2026-07-28"))
        self.assertAlmostEqual(bt.period_return(prices, "MNG", "2026-07-27", "2026-07-28"), 1315 / 1364 - 1)

    def test_asof_uses_last_known_value_only(self):
        pts = [("2026-01-05", 10.0, 1), ("2026-01-07", 12.0, 1)]
        self.assertEqual(bt.asof(pts, "2026-01-06")[1], 10.0)
        self.assertIsNone(bt.asof(pts, "2026-01-01"))


if __name__ == "__main__":
    unittest.main()
