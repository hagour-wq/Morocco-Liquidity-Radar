import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

DASH=Path("data/dashboard.json")
HIST=Path("data/market_history.json")

def clamp(x,a=-100,b=100): return max(a,min(b,x))

def pct(a,b):
    return None if b in (None,0) or a is None else (a/b-1)*100

def market_flow_score(rows):
    """Transparent V1 score. Requires >=20 official daily observations."""
    if len(rows)<20: return None, {"reason":"minimum_20_sessions"}
    r=rows[-1]; prev=rows[-2]
    vols=[x.get("volume_mad") for x in rows[-20:] if x.get("volume_mad") is not None]
    if len(vols)<15 or r.get("masi") is None or prev.get("masi") is None: return None,{"reason":"insufficient_fields"}
    ret1=pct(r["masi"],prev["masi"]) or 0
    ret5=pct(r["masi"],rows[-6]["masi"]) if len(rows)>=6 else 0
    volrel=r["volume_mad"]/mean(vols) if mean(vols) else 1
    breadth=r.get("breadth")
    # Momentum 45%, relative volume 30%, breadth 25%.
    momentum=clamp(ret1*12 + (ret5 or 0)*5)
    volume=clamp((volrel-1)*80)
    breadth_score=0 if breadth is None else clamp((breadth-0.5)*200)
    score=round(.45*momentum+.30*volume+.25*breadth_score)
    return score,{"ret_1d_pct":round(ret1,2),"ret_5d_pct":round(ret5 or 0,2),"volume_vs_20d":round(volrel,2),"breadth":breadth}

def main():
    d=json.loads(DASH.read_text(encoding="utf-8"))
    rows=json.loads(HIST.read_text(encoding="utf-8")) if HIST.exists() else []
    score,detail=market_flow_score(rows)
    d["scores"]["market_flow"]=score
    d["market_flow_detail"]=detail
    d["retrieved_at"]=datetime.now(timezone.utc).isoformat()
    if score is None:
        d["conclusion"]="Market Flow en calibration : le moteur exige au moins 20 séances officielles complètes avant d'émettre un signal."
    DASH.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding="utf-8")

if __name__=="__main__": main()
