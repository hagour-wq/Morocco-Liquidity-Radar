import json
from datetime import datetime, timezone, date
from pathlib import Path
from statistics import mean

DASH=Path("data/dashboard.json")
HIST=Path("data/market_history.json")

def clamp(x,a=-100,b=100): return max(a,min(b,x))
def pct(a,b): return None if b in (None,0) or a is None else (a/b-1)*100

def gap_days(a,b): return (date.fromisoformat(b)-date.fromisoformat(a)).days
def latest_contiguous(rows,max_gap=10):
    if not rows:return []
    start=len(rows)-1
    while start>0 and gap_days(rows[start-1]["date"],rows[start]["date"])<=max_gap:start-=1
    return rows[start:]

def market_flow_score(rows):
    rows=latest_contiguous(rows)
    if len(rows)<6: return None,{"reason":"minimum_6_sessions","confidence":"low","coverage":0}
    r,prev=rows[-1],rows[-2]
    if r.get("masi") is None or prev.get("masi") is None:
        return None,{"reason":"missing_masi","confidence":"low","coverage":0}
    ret1=pct(r["masi"],prev["masi"]) or 0
    ret5=pct(r["masi"],rows[-6]["masi"]) or 0
    ret20=pct(r["masi"],rows[-21]["masi"]) if len(rows)>=21 else None
    parts=[("momentum",clamp(ret1*12+ret5*5),45)]
    detail={"ret_1d_pct":round(ret1,2),"ret_5d_pct":round(ret5,2),"ret_20d_pct":round(ret20,2) if ret20 is not None else None}
    vols=[x.get("volume_mad") for x in rows[-20:] if x.get("volume_mad") is not None]
    if r.get("volume_mad") is not None and len(vols)>=5 and mean(vols):
        vr=r["volume_mad"]/mean(vols); parts.append(("volume",clamp((vr-1)*80),30))
        detail["volume_vs_available_avg"]=round(vr,2); detail["volume_sessions"]=len(vols)
    else: detail["volume_vs_available_avg"]=None
    breadth=r.get("breadth")
    if breadth is not None: parts.append(("breadth",clamp((breadth-.5)*200),25))
    detail["breadth"]=breadth
    w=sum(x[2] for x in parts); score=round(sum(v*wt for _,v,wt in parts)/w)
    detail["coverage"]=round(w/100,2); detail["components_used"]=[x[0] for x in parts]
    detail["confidence"]="high" if w>=75 and len(rows)>=20 else ("medium" if w>=70 else "low")
    return score,detail

def regime(score):
    if score is None:return "CALIBRATION"
    if score>=60:return "STRONG RISK-ON"
    if score>=20:return "RISK-ON"
    if score>=-19:return "NEUTRAL"
    if score>=-59:return "RISK-OFF"
    return "STRONG RISK-OFF"

def history_quality(rows,max_gap=10):
    if not rows:return {"sessions":0,"blocks":0,"first_date":None,"last_date":None,"largest_gap_days":None}
    gaps=[gap_days(rows[i-1]["date"],rows[i]["date"]) for i in range(1,len(rows))]
    return {"sessions":len(rows),"blocks":1+sum(g>max_gap for g in gaps),"first_date":rows[0]["date"],"last_date":rows[-1]["date"],
      "largest_gap_days":max(gaps) if gaps else 0,"latest_contiguous_sessions":len(latest_contiguous(rows))}

def main():
    d=json.loads(DASH.read_text(encoding="utf-8"))
    rows=json.loads(HIST.read_text(encoding="utf-8")) if HIST.exists() else []
    score,detail=market_flow_score(rows); d["scores"]["market_flow"]=score
    available=[]
    for key,w in [("liquidity",50),("market_flow",35),("global",15)]:
        v=d["scores"].get(key)
        if v is not None: available.append((v,w))
    w=sum(x[1] for x in available)
    d["composite"]=round(sum(v*wt for v,wt in available)/w) if w else None
    d["composite_coverage"]=round(w/100,2)
    d["regime"]=regime(d["composite"]) if w>=85 else "CALIBRATION"
    d["market_flow_detail"]=detail
    d["retrieved_at"]=datetime.now(timezone.utc).isoformat()
    d["as_of"]=rows[-1]["date"] if rows else d.get("as_of")
    d["market_data_status"]="STALE_OR_CURRENT_BY_AS_OF" if rows else "NO_MARKET_DATA"
    if rows:
        vals=[x["masi"] for x in rows if x.get("masi") is not None]
        latest=rows[-1]["masi"]
        peak=max(vals)
        d["market_snapshot"]={
          "masi":latest,
          "drawdown_from_sample_peak_pct":round(pct(latest,peak),2),
          "sample_peak":peak,
          "sample_low":min(vals),
          "sessions":len(latest_contiguous(rows))
        }
    if score is None:
        d["conclusion"]="Market Flow en calibration : historique MASI insuffisant."
    else:
        tone="positif" if score>=20 else "négatif" if score<=-20 else "neutre"
        d["conclusion"]=f"Market Flow {tone} ({score:+d}). Momentum 1 séance {detail['ret_1d_pct']:+.2f}% et 5 séances {detail['ret_5d_pct']:+.2f}%. Couverture {detail['coverage']*100:.0f}%."
    d.setdefault("data_quality",{})["market_history_sessions"]=len(rows)
    d["data_quality"]["history"]=history_quality(rows)
    d["data_quality"]["market_flow_coverage"]=detail.get("coverage",0)
    d["data_quality"]["composite_status"]=d["regime"]
    DASH.write_text(json.dumps(d,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

if __name__=="__main__": main()
