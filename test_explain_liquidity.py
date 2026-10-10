"""Lecture en clair du score fondamental et répartition de l'épargne OPCVM (AMMC)."""
import json, unittest
from pathlib import Path
import explain_fundamentals as xf
import build_liquidity_view as lv


def item(t, model="corporate", score=60, comp=None, **kw):
    base = {"ticker": t, "model": model, "score": score, "components": comp or {"valuation": 70, "quality": 70, "growth": 50, "structure": 50, "dividend": 40},
            "pe": 12.0, "pb": 1.5, "roe_pct": 18.0, "dividend_yield_pct": 3.0, "indicators": {}, "missing_components": [], "liquidity": {"tier": "élevée"}}
    base.update(kw)
    return base


class ExplainTests(unittest.TestCase):
    def test_profiles_and_messages(self):
        a = item("A")
        b = item("B", comp={"valuation": 20, "quality": 70, "growth": 50, "structure": 50, "dividend": 50}, pe=40.0)
        c = item("C", missing_components=["structure"], comp={"valuation": 70, "quality": 70, "growth": 50, "structure": None, "dividend": 50})
        d = item("D", liquidity={"tier": "faible", "avg_turnover_mad_20d": 20000})
        meds = xf.peer_medians([a, b, c, d])
        for x in (a, b, c, d):
            xf.explain(x, meds)
        self.assertEqual(a["profile"], "Solide")                      # dividende faible n'entre pas dans le profil
        self.assertTrue(any(s.startswith("Valorisation attractive") for s in a["strengths"]))
        self.assertEqual(b["profile"], "Contrasté")
        self.assertTrue(any(s.startswith("Valorisation exigeante") for s in b["watchpoints"]))
        self.assertEqual(c["profile"], "Incomplet")
        self.assertEqual(d["profile"], "Contrasté")
        self.assertTrue(any("Liquidité faible" in s for s in d["watchpoints"]))
        self.assertEqual(meds["corporate"]["pe"], 12.0)

    def test_exceptional_profit_flagged(self):
        x = item("X", indicators={"net_income_growth_pct": 287.0})
        xf.explain(x, xf.peer_medians([x]))
        self.assertTrue(any("élément exceptionnel" in s for s in x["watchpoints"]))


class LiquidityViewTests(unittest.TestCase):
    def test_file_dates(self):
        self.assertEqual(lv.file_date("https://www.ammc.ma/sites/default/files/STAT_OPCVM_HEBDO_AMMC_02102026.xls"), "2026-10-02")
        self.assertEqual(lv.file_date("https://www.ammc.ma/sites/default/files/STAT_OPCVM_HEBDO_AMMC%2018-09-2026.xls"), "2026-09-18")
        self.assertEqual(lv.file_date("https://www.ammc.ma/sites/default/files/STAT-OPCVM-HEBDO-AMMC-11092026.xlsx"), "2026-09-11")

    def test_flow_is_nav_change_net_of_performance(self):
        prev = {"nav": {"Actions": {"amount": 100.0}}}
        cur = {"nav": {"Actions": {"amount": 105.0}}, "performance": {"Actions": {"weekly_pct": 2.0}}}
        f = lv.flows(cur, prev)["Actions"]
        self.assertEqual((f["flow_mad"], f["market_effect_mad"]), (3, 2))   # 105 − 100 × 1,02 = 3 ; effet marché 2

    def test_real_ammc_snapshots(self):
        inp = json.loads(Path("data/liquidity_inputs.json").read_text(encoding="utf-8"))
        out = lv.build(inp, {})
        self.assertAlmostEqual(sum(c["share_pct"] for c in out["categories"]), 100, delta=0.1)
        contractuel = [c for c in out["categories"] if c["category"] == "Contractuel"]
        if contractuel:
            self.assertIsNone(contractuel[0]["flow_4w_mad"])    # pas d'indice de performance : flux non estimé, jamais 0
        self.assertTrue(all(w["from"] < w["to"] for w in out["weeks"]))


if __name__ == "__main__":
    unittest.main()
