"""Equity research ranking: evidence-first, no forecasts or fabricated returns.
Fundamental issuer records require dated inputs with source URL. Short-term
signals require enough per-security OHLCV observations and historical continuity.
"""
import json,math
from pathlib import Path
from datetime import date,datetime,timezone
ROOT=Path("data")
def load(name,default):
 p=ROOT/name
 return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default
def valid(v):
 return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)
def clamp(v):return max(0,min(100,round(v,1)))
def ratio(v,lo,hi,reverse=False):
 if not valid(v):return None
 z=clamp(100*(v-lo)/(hi-lo))
 return 100-z if reverse else z
def evaluate_fundamental(x):
 required=("ticker","name","reference_date","source_url","price_mad","eps_mad","book_value_per_share_mad","roe_pct","revenue_growth_pct","net_debt_ebitda","dividend_per_share_mad")
 missing=[k for k in required if x.get(k) is None or x.get(k)==""]
 if missing:return {"ticker":x.get("ticker"),"name":x.get("name"),"status":"INSUFFICIENT_DATA","missing_fields":missing}
 try: age=(date.today()-date.fromisoformat(x["reference_date"])).days
 except (ValueError,TypeError):age=10000
 if x.get("sector","").casefold() in ("banques","banque","banking","assurances","assurance","insurance"):
  return {"ticker":x.get("ticker"),"name":x.get("name"),"status":"SECTOR_MODEL_PENDING","note":"Financial institutions require sector-specific solvency and valuation scoring."}
 if age<0 or age>550 or not str(x["source_url"]).startswith("https://"):
  return {"ticker":x.get("ticker"),"name":x.get("name"),"status":"STALE_OR_UNSOURCED"}
 p,eps,bv=x["price_mad"],x["eps_mad"],x["book_value_per_share_mad"]
 if not all(valid(v) for v in (p,eps,bv,x["roe_pct"],x["revenue_growth_pct"],x["net_debt_ebitda"],x["dividend_per_share_mad"])) or p<=0 or eps<=0 or bv<=0:
  return {"ticker":x.get("ticker"),"name":x.get("name"),"status":"NOT_COMPARABLE","note":"Requires positive EPS and book value; banks need sector-specific model."}
 pe=p/eps;pb=p/bv;yield_pct=100*x["dividend_per_share_mad"]/p
 components={"valuation":(ratio(pe,8,35,True)+ratio(pb,.8,6,True))/2,"quality":ratio(x["roe_pct"],0,25),"growth":ratio(x["revenue_growth_pct"],-10,20),"debt":ratio(x["net_debt_ebitda"],0,5,True),"income":ratio(yield_pct,0,7)}
 score=clamp(.30*components["valuation"]+.25*components["quality"]+.20*components["growth"]+.15*components["debt"]+.10*components["income"])
 return {"ticker":x["ticker"],"name":x["name"],"score":score,"status":"RESEARCH_ONLY","reference_date":x["reference_date"],"source_url":x["source_url"],"pe":round(pe,2),"pb":round(pb,2),"dividend_yield_pct":round(yield_pct,2),"components":{k:round(v,1) for k,v in components.items()},"note":"Cross-sector comparisons are indicative; bank/insurer metrics require separate methodology."}
def evaluate_technical(ticker,name,rows):
 rows=sorted((x for x in rows if valid(x.get("close")) and valid(x.get("volume")) and x.get("date")),key=lambda x:x["date"])
 if len(rows)<25:return {"ticker":ticker,"name":name,"status":"INSUFFICIENT_HISTORY","sessions":len(rows),"required_sessions":25}
 last=rows[-1]
 try:age=(date.today()-date.fromisoformat(last["date"])).days
 except (ValueError,TypeError):age=10000
 if age<0 or age>5:return {"ticker":ticker,"name":name,"status":"STALE_DATA","last_date":last["date"]}
 gaps=[(date.fromisoformat(rows[i]["date"])-date.fromisoformat(rows[i-1]["date"])).days for i in range(len(rows)-24,len(rows))]
 if any(g>5 or g<=0 for g in gaps):return {"ticker":ticker,"name":name,"status":"GAPPED_HISTORY"}
 closes=[x["close"] for x in rows];vols=[x["volume"] for x in rows]
 if min(closes[-25:])<=0 or sum(vols[-20:-1])<=0:return {"ticker":ticker,"name":name,"status":"INVALID_PRICES_OR_VOLUME"}
 r5=100*(closes[-1]/closes[-6]-1);r20=100*(closes[-1]/closes[-21]-1)
 sma20=sum(closes[-20:])/20
 vr=vols[-1]/(sum(vols[-20:-1])/19)
 daily=[closes[i]/closes[i-1]-1 for i in range(len(closes)-19,len(closes))]
 volatility=(sum(v*v for v in daily)/len(daily))**.5*100
 score=clamp(.35*ratio(r5,-8,8)+.25*ratio(r20,-15,15)+.20*ratio(closes[-1]/sma20,0.9,1.1)+.10*ratio(vr,0.5,2.0)+.10*ratio(volatility,0,5,True))
 return {"ticker":ticker,"name":name,"status":"RESEARCH_ONLY","score":score,"reference_date":last["date"],"return_5d_pct":round(r5,2),"return_20d_pct":round(r20,2),"volume_ratio":round(vr,2),"volatility_daily_pct":round(volatility,2),"note":"Technical ranking is not a forecast or expected return."}
def main():
 base=load("company_fundamentals.json",{"companies":[]})
 quotes=load("equity_history.json",{"companies":[]})
 fundamentals=[evaluate_fundamental(x) for x in base.get("companies",[])]
 technical=[evaluate_technical(x.get("ticker"),x.get("name"),x.get("rows",[])) for x in quotes.get("companies",[])]
 # Snapshot performance is displayed as an unranked watchlist only, never as a validated signal.
 dash=load("dashboard.json",{})
 rotation=dash.get("rotation",{})
 watch=[]
 for kind in ("leaders","laggards"):
  for x in rotation.get(kind,[]):
   watch.append({"ticker":x.get("ticker"),"name":x.get("name"),"change_1d_pct":x.get("change_pct"),"status":"SNAPSHOT_ONLY","reference_date":rotation.get("reference_date"),"note":"One-session movement; cannot rank expected profitability."})
 f_rank=sorted((x for x in fundamentals if x.get("score") is not None),key=lambda x:x["score"],reverse=True)
 t_rank=sorted((x for x in technical if x.get("score") is not None),key=lambda x:x["score"],reverse=True)
 result={"generated_at":datetime.now(timezone.utc).isoformat(),"status":"RESEARCH_ONLY","methodology":{"long_term":"Value 30%, quality 25%, growth 20%, leverage 15%, dividend 10%. Non-bank positive earnings comparables only.","short_term":"Momentum 5D 35%, 20D 25%, distance SMA20 20%, relative volume 10%, realized volatility 10%. At least 25 dated closes and daily volumes required.","warning":"Rankings indicate relative factor scores, NOT expected returns or guaranteed profitability. Missing data exclude candidates."},"long_term":{"ranked":f_rank,"excluded":[x for x in fundamentals if x.get("score") is None],"status":"AVAILABLE" if f_rank else "AWAITING_VERIFIED_FUNDAMENTALS"},"short_term":{"ranked":t_rank,"excluded":[x for x in technical if x.get("score") is None],"snapshot_watchlist":watch,"status":"AVAILABLE" if t_rank else "AWAITING_OHLCV_HISTORY"}}
 (ROOT/"equity_rankings.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print("Long-term eligible:",len(f_rank),"Short-term eligible:",len(t_rank),"Watchlist:",len(watch))
if __name__=="__main__":main()
