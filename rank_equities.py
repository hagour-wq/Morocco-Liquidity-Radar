"""Equity research ranking: evidence-first, no forecasts or fabricated returns.
Fundamental issuer records require dated inputs with source URL. Short-term
signals require enough per-security OHLCV observations and historical continuity.
"""
import json,math
import technical as ta
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
 if x.get("listing_exchange")!="Casablanca Stock Exchange" or x.get("listing_country")!="MA":
  return {"ticker":x.get("ticker"),"name":x.get("name"),"status":"EXCHANGE_NOT_VERIFIED","note":"Requires independently validated Casablanca listing; AMMC reporting alone is insufficient."}
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
TECH_MIN_SESSIONS=25
def _r(v,d=2):return None if v is None else round(v,d)
def evaluate_technical(ticker,name,rows):
 """Indicateurs complets (technical.py) sur le segment postérieur à la dernière opération sur titres présumée.
 Score = momentum 5J 35 % + 20J 25 % + position / tendance 20 % + volume relatif 10 % + volatilité 10 %."""
 if not ticker or not name:return {"ticker":ticker,"name":name,"status":"INVALID_INSTRUMENT","category":"NON_ANALYSABLE"}
 rows=sorted((x for x in rows if valid(x.get("close")) and x.get("date")),key=lambda x:x["date"])
 base={"ticker":ticker,"name":name,"category":"NON_ANALYSABLE"}
 if len(rows)<TECH_MIN_SESSIONS:return {**base,"status":"INSUFFICIENT_HISTORY","sessions":len(rows),"required_sessions":TECH_MIN_SESSIONS}
 ca=[i for i,x in enumerate(rows) if "corporate_action_suspected" in str(x.get("status",""))]
 seg=rows[ca[-1]:] if ca else rows
 if len(seg)<TECH_MIN_SESSIONS:return {**base,"status":"CORPORATE_ACTION_RECENT","corporate_action_date":rows[ca[-1]]["date"],"sessions_since":len(seg),"required_sessions":TECH_MIN_SESSIONS}
 soft=("validated","corporate_action_suspected","incomplete_volume")
 flagged=[x["date"] for x in seg[-TECH_MIN_SESSIONS:] if x.get("status") not in (None,)+soft]
 if flagged:return {**base,"status":"FLAGGED_DATA_IN_WINDOW","flagged_dates":flagged,"note":"Anomaly inside the 25-session window; no technical score."}
 last=seg[-1]
 try:age=(date.today()-date.fromisoformat(last["date"])).days
 except (ValueError,TypeError):age=10000
 if age<0 or age>5:return {**base,"status":"STALE_DATA","last_date":last["date"]}
 gaps=[(date.fromisoformat(seg[i]["date"])-date.fromisoformat(seg[i-1]["date"])).days for i in range(len(seg)-24,len(seg))]
 if any(g>5 or g<=0 for g in gaps):return {**base,"status":"GAPPED_HISTORY"}
 c=[x["close"] for x in seg]
 nt=lambda x,k:x["close"] if x.get("traded") is False and x.get(k) is None else x.get(k)  # séance sans échange : H = B = cours de référence
 h=[nt(x,"high") for x in seg];l=[nt(x,"low") for x in seg];v=[x.get("volume") if valid(x.get("volume")) else None for x in seg]
 avgv=ta.mean_known(v[-21:-1],15)
 if min(c[-25:])<=0:return {**base,"status":"INVALID_PRICES"}
 if v[-1] is None or not avgv:return {**base,"status":"VOLUME_UNAVAILABLE","note":"Volume de la dernière séance inconnu ou moins de 15 volumes connus sur 20 : pas de score."}
 r5,r20,r60=ta.ret(c,5),ta.ret(c,20),ta.ret(c,60)
 s20,s50,s200=ta.sma(c,20),ta.sma(c,50),ta.sma(c,200)
 vr=v[-1]/avgv
 vol=ta.realized_vol_annual(c,20)
 trend_ref,trend_basis=(s50,"MM50") if s50 else (s20,"MM20")
 comp={"momentum_5d":ratio(r5,-8,8),"momentum_20d":ratio(r20,-15,15),"trend":ratio(c[-1]/trend_ref,0.9,1.1),"volume":ratio(vr,0.5,2.0),"volatility":ratio(vol,10,60,True)}
 score=clamp(.35*comp["momentum_5d"]+.25*comp["momentum_20d"]+.20*comp["trend"]+.10*comp["volume"]+.10*comp["volatility"])
 liq=ta.liquidity(seg)
 m=ta.macd(c);bb=ta.bollinger(c);sr=ta.support_resistance(h,l);a=ta.atr(h,l,c)
 cat="ELIGIBLE" if liq and liq["tier"]!="faible" and liq["zero_volume_sessions"]==0 else "WATCH"
 incomplete=[x["date"] for x in seg[-60:] if x.get("incomplete_volume")]
 return {"ticker":ticker,"name":name,"status":"RESEARCH_ONLY","category":cat,"score":score,"reference_date":last["date"],"close":last["close"],
  "sessions_used":len(seg),"segment_start":seg[0]["date"],"corporate_action_date":rows[ca[-1]]["date"] if ca else None,
  "return_5d_pct":_r(r5),"return_20d_pct":_r(r20),"momentum_60d_pct":_r(r60),"volume_ratio":_r(vr),
  "volatility_annual_pct":_r(vol),"rsi14":_r(ta.rsi(c),1),"sma20":_r(s20),"sma50":_r(s50),"sma200":_r(s200),
  "close_vs_sma200_pct":_r(100*(c[-1]/s200-1)) if s200 else None,"trend_basis":trend_basis,
  "macd":{k:_r(x,3) for k,x in m.items()} if m else None,"atr14":_r(a),"atr14_pct":_r(100*a/c[-1]) if a else None,
  "bollinger":{k:_r(x,3) for k,x in bb.items()} if bb else None,"support_resistance":sr,"liquidity":liq,"incomplete_volume_dates":incomplete,
  "components":{k:round(x,1) for k,x in comp.items()},
  "unavailable":[k for k,x in (("sma50",s50),("sma200",s200),("rsi14",ta.rsi(c)),("macd",m),("atr14",a)) if x is None],
  "note":"Score de facteurs techniques sur cours bruts ; ce n'est ni une prévision ni une recommandation."}
def main():
 base=load("company_fundamentals.json",{"companies":[]})
 quotes=load("equity_history.json",{"companies":[]})
 fundamentals=[evaluate_fundamental(x) for x in base.get("companies",[])]
 technical=[evaluate_technical(x.get("ticker"),x.get("name"),x.get("rows",[])) if x.get("listing_exchange")=="Casablanca Stock Exchange" and x.get("listing_country")=="MA" else {"ticker":x.get("ticker"),"name":x.get("name"),"status":"EXCHANGE_NOT_VERIFIED"} for x in quotes.get("companies",[])]
 # Snapshot performance is displayed as an unranked watchlist only, never as a validated signal.
 dash=load("dashboard.json",{})
 rotation=dash.get("rotation",{})
 watch=[]
 for kind in ("leaders","laggards"):
  for x in rotation.get(kind,[]):
   watch.append({"ticker":x.get("ticker"),"name":x.get("name"),"change_1d_pct":x.get("change_pct"),"status":"SNAPSHOT_ONLY","reference_date":rotation.get("reference_date"),"note":"One-session movement; cannot rank expected profitability."})
 f_rank=sorted((x for x in fundamentals if x.get("score") is not None),key=lambda x:x["score"],reverse=True)
 t_rank=sorted((x for x in technical if x.get("category")=="ELIGIBLE"),key=lambda x:x["score"],reverse=True)
 t_watch=sorted((x for x in technical if x.get("category")=="WATCH"),key=lambda x:x["score"],reverse=True)
 result={"generated_at":datetime.now(timezone.utc).isoformat(),"status":"RESEARCH_ONLY","methodology":{"long_term":"Value 30%, quality 25%, growth 20%, leverage 15%, dividend 10%. Non-bank positive earnings comparables only.","short_term":"Momentum 5 séances 35 %, 20 séances 25 %, position clôture / MM50 (MM20 si < 50 séances) 20 %, volume relatif 10 %, volatilité annualisée 20 j (inverse) 10 %. Minimum 25 séances après toute opération sur titres présumée. ÉLIGIBLE : montant moyen 20 j ≥ 1 M MAD et aucune séance sans échange sur 60 j ; sinon À SURVEILLER. Volume inconnu (enregistrement incomplet de la source) exclu des moyennes, jamais compté comme zéro.","warning":"Rankings indicate relative factor scores, NOT expected returns or guaranteed profitability. Missing data exclude candidates."},"long_term":{"ranked":f_rank,"excluded":[x for x in fundamentals if x.get("score") is None],"status":"AVAILABLE" if f_rank else "AWAITING_VERIFIED_FUNDAMENTALS"},"short_term":{"ranked":t_rank,"watch":t_watch,"excluded":[x for x in technical if x.get("score") is None],"snapshot_watchlist":watch,"status":"AVAILABLE" if t_rank or t_watch else "AWAITING_OHLCV_HISTORY"}}
 (ROOT/"equity_rankings.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print("Long-term eligible:",len(f_rank),"Short-term eligible:",len(t_rank),"Short-term watch:",len(t_watch),"Snapshot watchlist:",len(watch))
if __name__=="__main__":main()
