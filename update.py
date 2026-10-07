import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

DASH=Path("data/dashboard.json")
HIST=Path("data/market_history.json")

def clamp(x,a=-100,b=100): return max(a,min(b,x))
def pct(a,b): return None if b in (None,0) or a is None else (a/b-1)*100

def market_flow_score(rows):
    """V2: score available components only; never invent missing data."""
    if len(rows)<6:
        return None,{"reason":"minimum_6_sessions","confidence":"low","coverage":0}
    r,prev=rows[-1],rows[-2]
    if r.get("masi") is None or prev.get("masi") is None:
        return None,{"reason":"missing_masi","confidence":"low","coverage":0}
    ret1=pct(r["masi"],prev["masi"]) or 0
    ret5=pct(r["masi"],rows[-6]["masi"]) or 0
    parts=[("momentum",clamp(ret1*12+ret5*5),45)]
    detail={"ret_1d_pct":round(ret1,2),"ret_5d_pct":round(ret5,2)}
    vols=[x.get("volume_mad") for x in rows[-20:] if x.get("volume_mad") is not None]
    if r.get("volume_mad") is not None and len(vols)>=5 and mean(vols):
        volrel=r["volume_mad"]/mean(vols)
        parts.append(("volume",clamp((volrel-1)*80),30))
        detail["volume_vs_available_avg"]=round(volrel,2)
        detail["volume_sessions"]=len(vols)
    else:
        detail["volume_vs_available_avg"]=None
    breadth=r.get("breadth")
    if breadth is not None:
        parts.append(("breadth",clamp((breadth-0.5)*200),25))
    detail["breadth"]=breadth
    total_w=sum(w for _,_,w in parts)
    score=round(sum(v*w for _,v,w in parts)/total_w)
    coverage=round(total_w/100,2)
    detail["coverage"]=coverage
    detail["components_used"]=[name for name,_,_ in parts]
    detail["confidence"]="high" if coverage>=0.75 and len(rows)>=20 else ("medium" if coverage>=0.70 else "low")
    return score,detail

def main():
    d=json.loads(DASH.read_text(encoding="utf-8"))
    rows=json.loads(HIST.read_text(encoding="utf-8")) if HIST.exists() else []
    score,detail=market_flow_score(rows)
    d["scores"]["market_flow"]=score
    d["market_flow_detail"]=detail
    d["retrieved_at"]=datetime.now(timezone.utc).isoformat()
    if score is None:
        d["conclusion"]="Market Flow en calibration : historique MASI insuffisant pour calculer le momentum 5 séances."
    DASH.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding="utf-8")

if __name__=="__main__": main()
