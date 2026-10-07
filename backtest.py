import json
from pathlib import Path

HIST=Path("data/market_history.json")
OUT=Path("data/backtest.json")

def pct(a,b):
    return None if not a or not b else (a/b-1)*100

def clamp(x,a=-100,b=100):
    return max(a,min(b,x))

def momentum_score(rows,i):
    if i<5: return None
    r1=pct(rows[i]["masi"],rows[i-1]["masi"]) or 0
    r5=pct(rows[i]["masi"],rows[i-5]["masi"]) or 0
    return round(clamp(r1*12+r5*5))

def main():
    rows=json.loads(HIST.read_text())
    obs=[]
    for i in range(5,len(rows)):
        s=momentum_score(rows,i)
        future={}
        for n,label in [(1,"fwd_1d_pct"),(5,"fwd_5d_pct"),(10,"fwd_10d_pct")]:
            future[label]=round(pct(rows[i+n]["masi"],rows[i]["masi"]),2) if i+n<len(rows) else None
        obs.append({"date":rows[i]["date"],"score":s,**future})
    usable=[x for x in obs if x["fwd_5d_pct"] is not None and x["score"]!=0]
    correct=sum(1 for x in usable if (x["score"]>0 and x["fwd_5d_pct"]>0) or (x["score"]<0 and x["fwd_5d_pct"]<0))
    out={
      "method":"Momentum-only diagnostic backtest; not a validated investment strategy.",
      "observations":len(obs),
      "usable_5d":len(usable),
      "directional_accuracy_5d_pct":round(correct/len(usable)*100,1) if usable else None,
      "sample_warning":"Very small sample. Expand history before interpreting accuracy.",
      "series":obs
    }
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n")

if __name__=="__main__": main()
