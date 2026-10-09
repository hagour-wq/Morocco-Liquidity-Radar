import math, unittest
import technical as ta


class IndicatorTests(unittest.TestCase):
    def test_insufficient_history_returns_none(self):
        x = [100.0] * 30
        self.assertIsNone(ta.sma(x, 50))
        self.assertIsNone(ta.sma(x, 200))
        self.assertIsNone(ta.rsi(x))          # 43 séances requises
        self.assertIsNone(ta.macd(x))         # 53 séances requises
        self.assertIsNone(ta.atr(x[:28], x[:28], x[:28]))  # 2n+1 = 29 séances requises

    def test_rsi_extremes(self):
        up = [100 + i for i in range(60)]
        self.assertEqual(ta.rsi(up), 100.0)
        down = [200 - i for i in range(60)]
        self.assertAlmostEqual(ta.rsi(down), 0.0, places=6)

    def test_macd_of_constant_series_is_zero(self):
        m = ta.macd([50.0] * 80)
        self.assertAlmostEqual(m["macd"], 0)
        self.assertAlmostEqual(m["histogram"], 0)

    def test_realized_vol_uses_standard_deviation(self):
        # croissance constante : écart-type nul (une moyenne quadratique donnerait > 0)
        g = [100 * 1.01 ** i for i in range(30)]
        self.assertAlmostEqual(ta.realized_vol_annual(g), 0.0, places=9)
        alt = [100, 101] * 15
        v = ta.realized_vol_annual(alt)
        r = abs(math.log(1.01))
        self.assertAlmostEqual(v, 100 * r * math.sqrt(20 / 19) * math.sqrt(252), places=6)

    def test_atr_constant_range(self):
        c = [100.0] * 40
        self.assertAlmostEqual(ta.atr([101.0] * 40, [99.0] * 40, c), 2.0)

    def test_atr_refuses_missing_ohlc(self):
        c = [100.0] * 40
        h = [101.0] * 39 + [None]
        self.assertIsNone(ta.atr(h, [99.0] * 40, c))

    def test_bollinger_and_support_resistance(self):
        x = [100.0] * 19 + [110.0]
        b = ta.bollinger(x)
        self.assertGreater(b["percent_b"], 1 - 1e-9)
        sr = ta.support_resistance([10 + i for i in range(25)], [5 + i for i in range(25)])
        self.assertEqual((sr["support"], sr["resistance"]), (10, 34))

    def test_liquidity_tiers_and_warning(self):
        rows = [{"turnover_mad": 2e6, "volume": 1000} for _ in range(60)]
        self.assertEqual(ta.liquidity(rows)["tier"], "moyenne")
        self.assertIsNone(ta.liquidity(rows)["warning"])
        rows[-1] = {"turnover_mad": 0, "volume": 0}
        low = [{"turnover_mad": 1e5, "volume": 10} for _ in range(59)] + [{"turnover_mad": 0, "volume": 0}]
        liq = ta.liquidity(low)
        self.assertEqual(liq["tier"], "faible")
        self.assertIn("1 séance(s) sans échange", liq["warning"])

    def test_unknown_volume_is_not_zero(self):
        rows = [{"turnover_mad": 2e6, "volume": 1000} for _ in range(59)] + [{"turnover_mad": None, "volume": None}]
        liq = ta.liquidity(rows)
        self.assertEqual(liq["zero_volume_sessions"], 0)
        self.assertEqual(liq["missing_volume_sessions"], 1)
        self.assertEqual(liq["avg_turnover_mad_20d"], 2_000_000)


if __name__ == "__main__":
    unittest.main()
