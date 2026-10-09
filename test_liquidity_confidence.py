"""Confiance du score de liquidité et lacunes calculées (audit 09/10/2026)."""
import unittest
from unittest.mock import patch
import update as up

class LiquidityConfidenceTests(unittest.TestCase):
    def score(self,comps):
        with patch.object(up,"LIQ") as liq:
            liq.exists.return_value=False
            return up.liquidity_score({"liquidity_detail":{"components":comps}})
    def test_estimated_component_caps_confidence(self):
        _,d=self.score({"opcvm":{"weight":60,"score":-10,"verified":True,"raw":{"sig":{"estimated":True}}},
                        "policy_rate":{"weight":40,"score":0,"verified":True,"raw":{}}})
        self.assertEqual(d["confidence"],"medium")
        self.assertEqual(d["estimated_components"],["opcvm"])
    def test_proxy_component_caps_confidence(self):
        _,d=self.score({"bank":{"weight":100,"score":-25,"verified":True,"raw":{"provenance":"DEPF; monthly directional proxy"}}})
        self.assertEqual(d["confidence"],"medium")
    def test_official_components_keep_high(self):
        _,d=self.score({"policy_rate":{"weight":100,"score":0,"verified":True,"raw":{"current_rate":2.25}}})
        self.assertEqual(d["confidence"],"high")
    def test_missing_priority_is_computed(self):
        d={"liquidity_detail":{"components":{"opcvm":{"verified":True,"age_days":10,"raw":{"s":{"estimated":True}}},"bam":{"verified":False}}}}
        out=up.missing_priority(d,[])
        self.assertTrue(any("opcvm estimée" in x for x in out))
        self.assertTrue(any("bam non vérifiée" in x for x in out))

if __name__=="__main__":unittest.main()
