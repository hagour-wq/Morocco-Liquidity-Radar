"""Fallback history provider for Casablanca-listed securities, with strict exchange/currency verification."""
import json,time
from datetime import datetime,timezone,date
from urllib.request import Request,urlopen
from urllib.parse import quote
from pathlib import Path
HIST=Path("data/equity_history.json")
DIAG=Path("data/equity_fallback_diagnostic.json")
DASH=Path("data/dashboard.json")
def candidates():
 d=json.loads(DASH.read_text())
 rot=d.get("rotation",{})
 result={}
 for key in ("leaders","laggards","active"):
  for x in rot.get(key,[]):
   sym=x.get("ticker")
   if sym and sym.isalnum() and 2<=len(sym)<=6:result[sym] = x.get("name") or sym
 return result
def history(symbol):
 url="https://query1.finance.yahoo.com/v8/finance/chart/"+quote(symbol+".CS",safe="")+"?range=2y&interval=1d"
 req=Request(url,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"})
 with urlopen(req,timeout=12) as response:obj=json.loads(response.read(9000000))
 x=(obj.get("chart",{}).get("result") or [None])[0]
 if not x:raise ValueError("no_chart_result")
 m=x.get("meta",{})
 exchange=str(m.get("exchangeName") or m.get("fullExchangeName") or "").upper()
 currency=str(m.get("currency") or "").upper()
 # Unambiguous Maroc evidence in exchange metadata required, not just '.CS' suffix.
 if currency!="MAD" or not any(s in exchange for s in ("CASA","MOROCC","CSE")):
  raise ValueError("unverified_exchange_currency: "+exchange+"/"+currency)
 times=x.get("timestamp") or []
 quotes=(x.get("indicators",{}).get("quote") or [{}])[0]
 closes=quotes.get("close") or []
 volumes=quotes.get("volume") or []
 rows={}
 for ts,cl,vol in zip(times,closes,volumes):
  if isinstance(cl,(int,float)) and isinstance(vol,(int,float)) and cl>0 and vol>=0:
   dt=datetime.fromtimestamp(ts,timezone.utc).date().isoformat()
   if dt<=date.today().isoformat():rows[dt]={"date":dt,"close":float(cl),"volume":float(vol),"quality":"secondary_market_history","source":"Yahoo Finance","source_url":url}
 if len(rows)<25:raise ValueError("insufficient_history_"+str(len(rows)))
 return sorted(rows.values(),key=lambda z:z["date"]),{"exchange":exchange,"currency":currency,"url":url}
def main():
 d={"checked_at":datetime.now(timezone.utc).isoformat(),"provider":"Yahoo Finance chart v8","accepted":[],"rejected":[],"status":"UNVERIFIED"}
 previous=json.loads(HIST.read_text()) if HIST.exists() else {"companies":[]}
 by={x["ticker"]:x for x in previous.get("companies",[])}
 for ticker,name in candidates().items():
  try:
   rows,meta=history(ticker)
   existing=by.get(ticker,{"ticker":ticker,"name":name,"rows":[]})
   index={x["date"]:x for x in existing.get("rows",[]) if x.get("date")}
   for x in rows:
    if x["date"] not in index or index[x["date"]].get("quality")!="official_json_history":index[x["date"]]=x
   existing.update({"ticker":ticker,"name":name,"rows":sorted(index.values(),key=lambda x:x["date"])})
   by[ticker]=existing
   d["accepted"].append({"ticker":ticker,"rows":len(rows),**meta})
  except Exception as e:d["rejected"].append({"ticker":ticker,"reason":str(e)[:180]})
  time.sleep(.15)
 d["status"]="SUCCESS" if d["accepted"] else "NO_VALIDATED_EQUITY_HISTORY"
 d["eligible_companies"]=len(d["accepted"])
 DIAG.write_text(json.dumps(d,ensure_ascii=False,indent=2)+"\n")
 if d["accepted"]:
  HIST.write_text(json.dumps({"schema_version":1,"updated_at":d["checked_at"],"companies":list(by.values())},ensure_ascii=False,indent=2)+"\n")
 print(json.dumps({"status":d["status"],"accepted":len(d["accepted"]),"rejected":len(d["rejected"])},ensure_ascii=False))
if __name__=="__main__":main()
