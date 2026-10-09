import unittest
from market_rotation import rotation


def comp(t, sector, closes, caps, turnovers):
    rows = [{"date": d, "close": c, "market_cap_mad": cap, "turnover_mad": tv, "traded": True, "status": "validated"}
            for d, c, cap, tv in zip(["2026-10-07", "2026-10-08", "2026-10-09"], closes, caps, turnovers)]
    return {"ticker": t, "name": t, "sector": sector, "rows": rows}


class RotationTests(unittest.TestCase):
    def test_cap_weighted_sector_and_liquidity_filter(self):
        cs = [comp(f"B{i}", "Banques", [100, 100, 101], [9e9, 9e9, 9e9], [5e6] * 3) for i in range(6)]
        cs += [comp(f"S{i}", "Mines", [100, 100, 98], [1e9, 1e9, 1e9], [5e6] * 3) for i in range(5)]
        cs.append(comp("ILQ", "Mines", [100, 100, 109], [1e8] * 3, [1000] * 3))   # +9 % sur 1 000 MAD : écarté des hausses
        r = rotation(cs)
        self.assertEqual(r["reference_date"], "2026-10-09")
        self.assertEqual(r["sectors"][0], {"name": "Banques", "change_pct": 1.0})
        self.assertNotIn("ILQ", [x["ticker"] for x in r["leaders"]])
        self.assertEqual(r["breadth"]["advancers"], 7)
        self.assertEqual(r["active"][0]["volume_mad"], 5e6)


if __name__ == "__main__":
    unittest.main()
