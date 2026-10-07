import json
from pathlib import Path
from statistics import mean

HIST=Path("data/market_history.json"); OUT=Path("data/backtest.json")
def pct(a,b): return None if not a or not b else (a/b-1)*100
def clamp(x,a=-100,b=100): return max(a,min(b,x))
def score(rows,i):
    if i<5:return None
    return round(clamp((pct(rows[i]["masi"],rows[i-1]["masi"]) or 0)*12+(pct(rows[i]["masi"],rows[i-5]["masi"]) or 0)*5))

def horizon_stats(obs,key):
    u=[x for x in obs if x[key] is not None and x["score"] not in (None,0)]
    if not u:return {"n":0,"directional_accuracy_pct":None,"avg_forward_pct":None}
    ok=sum((x["score"]>0 and x[key]>0) or (x["score"]<0 and x[key]<0) for x in u)
    return {"n":len(u),"directional_accuracy_pct":round(ok/len(u)*100,1),"avg_forward_pct":round(mean(x[key] for x in u),2)}

def main():
    rows=json.loads(HIST.read_text(encoding="utf-8")); obs=[]
    for i in range(5,len(rows)):
        s=score(rows,i); x={"date":rows[i]["date"],"score":s}
        for n in [1,5,10,20]:
            x[f"fwd_{n}d_pct"]=round(pct(rows[i+n]["masi"],rows[i]["masi"]),2) if i+n<len(rows) else None
        obs.append(x)
    stats={f"{n}d":horizon_stats(obs,f"fwd_{n}d_pct") for n in [1,5,10,20]}
    pos=[x for x in obs if x["score"] is not None and x["score"]>=20]
    neg=[x for x in obs if x["score"] is not None and x["score"]<=-20]
    out={"method":"Momentum diagnostic; not a validated investment strategy.","history_sessions":len(rows),"observations":len(obs),"horizons":stats,
      "signal_counts":{"risk_on_like":len(pos),"risk_off_like":len(neg)},
      "usable_5d":stats["5d"]["n"],"directional_accuracy_5d_pct":stats["5d"]["directional_accuracy_pct"],
      "sample_warning":"Interpret only after sufficient historical depth; no transaction costs or execution model.","series":obs}
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
if __name__=="__main__":main()
