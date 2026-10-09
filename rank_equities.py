"""Equity research ranking: evidence-first, no forecasts or fabricated returns.
Fundamental issuer records require dated inputs with source URL. Short-term
signals require enough per-security OHLCV observations and historical continuity.
"""
import json,math
import technical as ta
import equity_store
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
# Bornes de normalisation (0 → 100, linéaire, bornées) — conventions de marché documentées dans le README.
FUND_BOUNDS={
 "bank":{"pe":(6,20,True),"pb":(0.8,3.5,True),"roe":(5,20,False),"cost_income":(35,65,True),"pnb_growth":(-5,15,False),
         "ni_growth":(-20,40,False),"cost_of_risk_loans":(0.3,2.5,True),"dividend_yield":(0,7,False)},
 "corporate":{"pe":(8,30,True),"pb":(1,8,True),"roe":(0,30,False),"operating_margin":(0,40,False),"revenue_growth":(-10,25,False),
              "ni_growth":(-20,40,False),"net_debt_ebitda":(0,4,True),"equity_ratio":(10,60,False),"dividend_yield":(0,7,False)},
 # assurances (IFRS 17) : charges / produits des activités d'assurance (proxy du ratio combiné, brut de réassurance),
 # capitaux propres / total bilan faute de marge de solvabilité publiée dans le document
 "insurance":{"pe":(6,25,True),"pb":(0.8,4,True),"roe":(5,20,False),"insurance_expense_ratio":(80,100,True),"revenue_growth":(-5,15,False),
              "ni_growth":(-20,40,False),"equity_ratio":(5,30,False),"dividend_yield":(0,7,False)}}
FUND_WEIGHTS={"valuation":30,"quality":25,"growth":20,"structure":15,"dividend":10}
FUND_MAX_AGE_DAYS=548   # comptes annuels : valables jusqu'à ~18 mois après la clôture
def _avg(xs):
 xs=[x for x in xs if x is not None]
 return sum(xs)/len(xs) if xs else None
def evaluate_fundamental(c,price=None,price_date=None,dividend_yield=None,volatility=None,liquidity_tier=None):
 """Score fondamental /100 par modèle sectoriel (banques / sociétés non financières).
 Valorisation 30 %, qualité 25 %, croissance 20 %, structure / risque 15 %, dividende 10 %.
 Composante manquante : score calculé sur les poids disponibles, marqué partiel et classé « À surveiller »."""
 t,name=c.get("ticker"),c.get("name")
 base={"ticker":t,"name":name,"model":c.get("model"),"fiscal_year":c.get("fiscal_year"),"source_url":c.get("url"),"accounts_scope":c.get("scope"),"text_source":c.get("text_source"),"category":"NON_ANALYSABLE"}
 if c.get("listing_exchange")!="Casablanca Stock Exchange" or c.get("listing_country")!="MA":
  return {**base,"status":"EXCHANGE_NOT_VERIFIED","note":"Cotation à Casablanca non vérifiée."}
 if c.get("status")!="VERIFIED":
  return {**base,"status":c.get("status") or "INSUFFICIENT_DATA","note":c.get("reason") or "; ".join((c.get("errors") or [])+["manquant : "+", ".join(c.get("missing") or [])] if c.get("missing") else (c.get("errors") or [])) or None}
 d=c.get("derived",{})
 try:age=(date.fromisoformat(price_date)-date.fromisoformat(c["period_end"])).days if price_date else None
 except (ValueError,TypeError,KeyError):age=None
 if age is None or age<0 or age>FUND_MAX_AGE_DAYS:return {**base,"status":"STALE_OR_UNDATED","note":"Comptes de plus de 18 mois ou cours indisponible."}
 if not valid(price) or price<=0:return {**base,"status":"NO_PRICE"}
 eps,bv=d.get("eps_current_shares_mad"),d.get("book_value_per_share_mad")
 pe=price/eps if valid(eps) and eps>0 else None
 pb=price/bv if valid(bv) and bv>0 else None
 m=c["model"];B=FUND_BOUNDS[m]
 r=lambda k,x:None if x is None else ratio(x,B[k][0],B[k][1],B[k][2])
 # perte : le PER n'est pas défini mais la valorisation par les bénéfices est la pire possible (0), jamais ignorée
 pe_score=0.0 if valid(eps) and eps<=0 else r("pe",pe)
 comp={"valuation":_avg([pe_score,r("pb",pb)]),"dividend":r("dividend_yield",dividend_yield)}
 if m=="bank":
  comp.update(quality=_avg([r("roe",d.get("roe_pct")),r("cost_income",d.get("cost_income_pct"))]),
              growth=_avg([r("pnb_growth",d.get("pnb_growth_pct")),r("ni_growth",d.get("net_income_growth_pct"))]),
              structure=r("cost_of_risk_loans",d.get("cost_of_risk_to_loans_pct")))
 elif m=="insurance":
  comp.update(quality=_avg([r("roe",d.get("roe_pct")),r("insurance_expense_ratio",d.get("insurance_expense_ratio_pct"))]),
              growth=_avg([r("revenue_growth",d.get("revenue_growth_pct")),r("ni_growth",d.get("net_income_growth_pct"))]),
              structure=r("equity_ratio",d.get("equity_ratio_pct")))
 else:
  comp.update(quality=_avg([r("roe",d.get("roe_pct")),r("operating_margin",d.get("operating_margin_pct"))]),
              growth=_avg([r("revenue_growth",d.get("revenue_growth_pct")),r("ni_growth",d.get("net_income_growth_pct"))]),
              structure=r("net_debt_ebitda",d.get("net_debt_to_ebitda")) if d.get("net_debt_to_ebitda") is not None else r("equity_ratio",d.get("equity_ratio_pct")))
 have={k:v for k,v in comp.items() if v is not None}
 missing=[k for k in FUND_WEIGHTS if k not in have]
 w=sum(FUND_WEIGHTS[k] for k in have)
 score=clamp(sum(FUND_WEIGHTS[k]*have[k] for k in have)/w) if w else None
 risk="élevé" if (volatility or 0)>35 or liquidity_tier=="faible" else "faible" if volatility is not None and volatility<20 and liquidity_tier=="élevée" else "moyen" if volatility is not None else None
 return {**base,"status":"RESEARCH_ONLY","category":"ELIGIBLE" if not missing else "WATCH","score":score,"partial":bool(missing),"missing_components":missing,
  "price_mad":price,"price_date":price_date,"pe":round(pe,2) if pe else None,"pb":round(pb,2) if pb else None,
  "roe_pct":round(d["roe_pct"],2) if valid(d.get("roe_pct")) else None,"dividend_yield_pct":dividend_yield,"risk_level":risk,
  "eps_mad":round(eps,2) if valid(eps) else None,"book_value_per_share_mad":round(bv,2) if valid(bv) else None,
  "indicators":{k:(round(v,2) if isinstance(v,float) else v) for k,v in d.items() if k.endswith("_pct") or k=="net_debt_to_ebitda"},
  "components":{k:(round(v,1) if v is not None else None) for k,v in comp.items()},"notes":c.get("notes"),
  "note":"Score de facteurs fondamentaux sur comptes publiés ; ce n'est ni une prévision ni une recommandation."}
TECH_MIN_SESSIONS=25
MAX_GAP_DAYS=7  # fermetures légales observées jusqu'à 6 jours (Aïd al-Fitr 2024, Aïd al-Adha 2026) ; au-delà : trou de données
def _r(v,d=2):return None if v is None else round(v,d)
def evaluate_technical(ticker,name,rows,as_of=None):
 as_of=as_of or date.today()
 rows=[x for x in rows if x.get("date") and x["date"]<=as_of.isoformat()]  # aucun regard vers le futur
 raw_rows=sorted(rows,key=lambda x:x["date"])
 """Indicateurs complets (technical.py) sur le segment postérieur à la dernière opération sur titres présumée.
 Score = momentum 5J 35 % + 20J 25 % + position / tendance 20 % + volume relatif 10 % + volatilité 10 %."""
 if not ticker or not name:return {"ticker":ticker,"name":name,"status":"INVALID_INSTRUMENT","category":"NON_ANALYSABLE"}
 raw=len(rows)
 # séances recopiées par la source (ex. 17/09/2026) : exclues ; cours nuls (titre suspendu) : exclus
 rows=sorted((x for x in rows if valid(x.get("close")) and x["close"]>0 and x.get("date") and "stale_copy" not in str(x.get("status",""))),key=lambda x:x["date"])
 base={"ticker":ticker,"name":name,"category":"NON_ANALYSABLE"}
 if len(rows)<TECH_MIN_SESSIONS:
  if raw>=TECH_MIN_SESSIONS:return {**base,"status":"NO_VALID_PRICES","sessions":raw,"valid_price_sessions":len(rows),"note":"Cours nuls ou absents : titre vraisemblablement suspendu de cotation."}
  return {**base,"status":"INSUFFICIENT_HISTORY","sessions":len(rows),"required_sessions":TECH_MIN_SESSIONS}
 ca=[i for i,x in enumerate(rows) if "corporate_action_suspected" in str(x.get("status",""))]
 seg=rows[ca[-1]:] if ca else rows
 if len(seg)<TECH_MIN_SESSIONS:return {**base,"status":"CORPORATE_ACTION_RECENT","corporate_action_date":rows[ca[-1]]["date"],"sessions_since":len(seg),"required_sessions":TECH_MIN_SESSIONS}
 soft={"validated","corporate_action_suspected","incomplete_volume"}
 flagged=[x["date"] for x in seg[-TECH_MIN_SESSIONS:] if not set(str(x.get("status") or "validated").split(","))<=soft]
 if flagged:return {**base,"status":"FLAGGED_DATA_IN_WINDOW","flagged_dates":flagged,"note":"Anomaly inside the 25-session window; no technical score."}
 last=seg[-1]
 try:age=(as_of-date.fromisoformat(last["date"])).days
 except (ValueError,TypeError):age=10000
 if age<0 or age>MAX_GAP_DAYS:return {**base,"status":"STALE_DATA","last_date":last["date"]}
 gaps=[(date.fromisoformat(seg[i]["date"])-date.fromisoformat(seg[i-1]["date"])).days for i in range(len(seg)-24,len(seg))]
 if any(g>MAX_GAP_DAYS or g<=0 for g in gaps):return {**base,"status":"GAPPED_HISTORY"}
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
 stale=[x["date"] for x in raw_rows[-60:] if "stale_copy" in str(x.get("status",""))]
 return {"ticker":ticker,"name":name,"status":"RESEARCH_ONLY","category":cat,"score":score,"reference_date":last["date"],"close":last["close"],
  "sessions_used":len(seg),"segment_start":seg[0]["date"],"corporate_action_date":rows[ca[-1]]["date"] if ca else None,
  "return_5d_pct":_r(r5),"return_20d_pct":_r(r20),"momentum_60d_pct":_r(r60),"volume_ratio":_r(vr),
  "volatility_annual_pct":_r(vol),"rsi14":_r(ta.rsi(c),1),"sma20":_r(s20),"sma50":_r(s50),"sma200":_r(s200),
  "close_vs_sma200_pct":_r(100*(c[-1]/s200-1)) if s200 else None,"trend_basis":trend_basis,
  "macd":{k:_r(x,3) for k,x in m.items()} if m else None,"atr14":_r(a),"atr14_pct":_r(100*a/c[-1]) if a else None,
  "bollinger":{k:_r(x,3) for k,x in bb.items()} if bb else None,"support_resistance":sr,"liquidity":liq,"incomplete_volume_dates":incomplete,"excluded_stale_dates":stale,
  "components":{k:round(x,1) for k,x in comp.items()},
  "unavailable":[k for k,x in (("sma50",s50),("sma200",s200),("rsi14",ta.rsi(c)),("macd",m),("atr14",a)) if x is None],
  "note":"Score de facteurs techniques sur cours bruts ; ce n'est ni une prévision ni une recommandation."}
def issuer_facts(r,close,ref_date,divs=None,ca_dates=()):
 """ISIN et dividendes. Avec le calendrier officiel (data/dividends.json) : rendement = dividendes ordinaires et
 optionnels détachés sur les 12 derniers mois / dernier cours (exceptionnels affichés à part, hors rendement).
 Un dividende détaché AVANT une opération sur titres présumée n'est pas comparable au cours actuel : on retient alors
 le montant ajusté du bulletin de la cote s'il porte sur ce détachement, sinon il est écarté (et signalé).
 Sans calendrier : dernier dividende du bulletin, seulement si détaché il y a moins de 15 mois."""
 r=r or {}
 out={"isin":r.get("isin"),"last_dividend_mad":r.get("last_dividend_mad"),"dividend_fiscal_year":r.get("dividend_fiscal_year"),"dividend_ex_date":r.get("dividend_ex_date")}
 if divs is not None and ref_date and valid(close) and close>0:
  try:
   d0=date.fromisoformat(ref_date);lo=date.fromordinal(d0.toordinal()-365).isoformat()
  except ValueError:d0=None
  if d0:
   win=[d for d in divs if lo<d["ex_date"]<=ref_date];reg=0.0;exc=0.0;notes=[]
   for d in win:
    amt=d["amount_mad"]
    if any(d["ex_date"]<c<=ref_date for c in ca_dates):
     if r.get("dividend_ex_date")==d["ex_date"] and valid(r.get("last_dividend_mad")):
      amt=r["last_dividend_mad"];notes.append(f"dividende du {d['ex_date']} ({d['amount_mad']} MAD) ajusté de l'opération sur titres : {amt} MAD (bulletin de la cote)")
     else:
      notes.append(f"dividende du {d['ex_date']} écarté : détaché avant une opération sur titres, montant ajusté inconnu");continue
    if d["type"]=="Exceptionnel":exc+=amt
    else:reg+=amt
   out.update(dividend_yield_pct=round(100*reg/close,2) if reg>0 else None,dividends_12m_mad=round(reg,4),
              exceptional_dividends_12m_mad=round(exc,4) or None,dividend_events_12m=len(win),dividend_notes=notes or None,
              dividend_yield_basis="dividendes ordinaires détachés sur 12 mois (calendrier officiel) / dernier cours" if reg>0 else "aucun dividende ordinaire détaché sur 12 mois (calendrier officiel)")
   if win:
    out.update(dividend_ex_date=win[0]["ex_date"],last_dividend_mad=win[0]["amount_mad"])
   return out
 try:recent=(date.fromisoformat(ref_date)-date.fromisoformat(r["dividend_ex_date"])).days<=456
 except (TypeError,ValueError,KeyError):recent=False
 out["dividend_yield_pct"]=round(100*r["last_dividend_mad"]/close,2) if recent and valid(r.get("last_dividend_mad")) and valid(close) and close>0 else None
 out["dividend_yield_basis"]="dernier dividende détaché / dernier cours" if out["dividend_yield_pct"] is not None else ("dernier dividende détaché il y a plus de 15 mois" if r.get("dividend_ex_date") else "aucun dividende publié au bulletin")
 return out
def main():
 base=load("company_fundamentals.json",{"companies":[]})
 quotes={"companies":equity_store.load_all()}
 tech_by={}
 fundamentals=[]
 technical=[evaluate_technical(x.get("ticker"),x.get("name"),x.get("rows",[])) if x.get("listing_exchange")=="Casablanca Stock Exchange" and x.get("listing_country")=="MA" else {"ticker":x.get("ticker"),"name":x.get("name"),"status":"EXCHANGE_NOT_VERIFIED"} for x in quotes.get("companies",[])]
 sectors={x.get("ticker"):x.get("sector") for x in quotes.get("companies",[])}
 ref=load("issuer_reference.json",{}).get("issuers",{})
 cal=load("dividends.json",{}).get("companies")
 cas={x.get("ticker"):[r["date"] for r in x.get("rows",[]) if "corporate_action_suspected" in str(r.get("status",""))] for x in quotes.get("companies",[])}
 divs_of=lambda t:None if cal is None else (cal.get(t) or {}).get("dividends",[])
 for x in technical:
  x["sector"]=sectors.get(x.get("ticker"))
  r=ref.get(x.get("ticker"))
  if r or cal is not None:x.update(issuer_facts(r,x.get("close"),x.get("reference_date"),divs_of(x.get("ticker")),cas.get(x.get("ticker"),())))
 # Snapshot performance is displayed as an unranked watchlist only, never as a validated signal.
 dash=load("dashboard.json",{})
 rotation=dash.get("rotation",{})
 watch=[]
 for kind in ("leaders","laggards"):
  for x in rotation.get(kind,[]):
   watch.append({"ticker":x.get("ticker"),"name":x.get("name"),"change_1d_pct":x.get("change_pct"),"status":"SNAPSHOT_ONLY","reference_date":rotation.get("reference_date"),"note":"One-session movement; cannot rank expected profitability."})
 tech_by={x.get("ticker"):x for x in technical}
 names={x.get("ticker"):x.get("name") for x in quotes.get("companies",[])}
 last={x.get("ticker"):next((r for r in reversed(x.get("rows",[])) if valid(r.get("close")) and r["close"]>0 and "stale_copy" not in str(r.get("status",""))),None) for x in quotes.get("companies",[])}
 for c in base.get("companies",[]):
  t=c.get("ticker");tx=tech_by.get(t,{});lr=last.get(t) or {}
  c=dict(c,name=c.get("name") or names.get(t),sector=sectors.get(t))
  dy=tx.get("dividend_yield_pct")
  if "dividend_yield_pct" not in tx and valid(lr.get("close")) and (ref.get(t) or cal is not None):dy=issuer_facts(ref.get(t),lr["close"],lr.get("date"),divs_of(t),cas.get(t,())).get("dividend_yield_pct")
  x=evaluate_fundamental(c,lr.get("close"),lr.get("date"),dy,tx.get("volatility_annual_pct"),(tx.get("liquidity") or {}).get("tier"))
  x["sector"]=sectors.get(t);fundamentals.append(x)
 f_rank=sorted((x for x in fundamentals if x.get("category")=="ELIGIBLE"),key=lambda x:x["score"],reverse=True)
 f_watch=sorted((x for x in fundamentals if x.get("category")=="WATCH"),key=lambda x:x["score"],reverse=True)
 t_rank=sorted((x for x in technical if x.get("category")=="ELIGIBLE"),key=lambda x:x["score"],reverse=True)
 t_watch=sorted((x for x in technical if x.get("category")=="WATCH"),key=lambda x:x["score"],reverse=True)
 result={"generated_at":datetime.now(timezone.utc).isoformat(),"status":"RESEARCH_ONLY","methodology":{"long_term":"Valorisation 30 % (PER, P/B), qualité 25 % (ROE + coefficient d'exploitation pour les banques, marge d'exploitation sinon), croissance 20 % (PNB ou chiffre d'affaires, résultat net), structure / risque 15 % (coût du risque / encours pour les banques ; dette nette / EBITDA sinon, ou à défaut autonomie financière = capitaux propres / total bilan), dividende 10 %. Bornes propres à chaque modèle sectoriel. Composante manquante : score partiel, catégorie À SURVEILLER. Comptes publiés de moins de 18 mois uniquement.","short_term":"Momentum 5 séances 35 %, 20 séances 25 %, position clôture / MM50 (MM20 si < 50 séances) 20 %, volume relatif 10 %, volatilité annualisée 20 j (inverse) 10 %. Minimum 25 séances après toute opération sur titres présumée. ÉLIGIBLE : montant moyen 20 j ≥ 1 M MAD et aucune séance sans échange sur 60 j ; sinon À SURVEILLER. Volume inconnu (enregistrement incomplet de la source) exclu des moyennes, jamais compté comme zéro.","warning":"Rankings indicate relative factor scores, NOT expected returns or guaranteed profitability. Missing data exclude candidates."},"long_term":{"ranked":f_rank,"watch":f_watch,"excluded":[x for x in fundamentals if x.get("score") is None],"coverage":{"issuers_in_registry":len(base.get("companies",[])),"listed":len(quotes.get("companies",[]))},"status":"AVAILABLE" if f_rank or f_watch else "AWAITING_VERIFIED_FUNDAMENTALS"},"short_term":{"ranked":t_rank,"watch":t_watch,"excluded":[x for x in technical if x.get("score") is None],"snapshot_watchlist":watch,"status":"AVAILABLE" if t_rank or t_watch else "AWAITING_OHLCV_HISTORY"}}
 (ROOT/"equity_rankings.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print("Long-term eligible:",len(f_rank),"Long-term watch:",len(f_watch),"Short-term eligible:",len(t_rank),"Short-term watch:",len(t_watch),"Snapshot watchlist:",len(watch))
if __name__=="__main__":main()
