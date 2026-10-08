"""Backfill official Casablanca historical instrument OHLCV via documented public website JSON API.
Historical rows are source-attributed, merged by ticker/date, and fail closed.
No price is imputed, forward-filled or manufactured.
"""
import json,os,re,time,ssl,certifi
from datetime import date,datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlencode
OUT=Path("data/equity_history.json")
DIAG=Path("data/equity_backfill_diagnostic.json")
BASE="https://www.casablanca-bourse.com/api/proxy/fr/api/bourse_data/instrument_history"
LIMIT=250
FIELDS="symbol,created,openingPrice,coursCourant,highPrice,lowPrice,cumulTitresEchanges,cumulVolumeEchange,totalTrades,capitalisation,coursAjuste,closingPrice,ratioConsolide"
def numeric(v):
 if isinstance(v,(int,float)) and not isinstance(v,bool):return float(v)
 if not isinstance(v,str):return None
 z=v.replace("\u202f","").replace("\xa0","").replace(" ","").replace(",",".")
 try:return float(z)
 except (ValueError,TypeError):return None
def request(offset):
 params={
  "fields[instrument_history]":FIELDS,
  "fields[instrument]":"symbol,libelleFR,libelleAR,libelleEN",
  "include":"symbol",
  "sort[date-seance][path]":"created",
  "sort[date-seance][direction]":"DESC",
  "filter[instrument-history-class][condition][path]":"symbol.codeClasse.field_code",
  "filter[instrument-history-class][condition][value]":"1",
  "filter[instrument-history-class][condition][operator]":"=",
  "filter[published]":"1",
  "filter[filter-date-start-vh-select][condition][path]":"field_seance_date",
  "filter[filter-date-start-vh-select][condition][operator]":">=",
  "filter[filter-date-start-vh-select][condition][value]":os.getenv("EQUITY_BACKFILL_START","2026-06-01"),
  "page[offset]":str(offset),"page[limit]":str(LIMIT)
 }
 url=BASE+"?"+urlencode(params)
 req=Request(url,headers={"User-Agent":"Mozilla/5.0","Accept":"application/vnd.api+json","Referer":"https://www.casablanca-bourse.com/fr/market-data/Cours"})
 tls=ssl.create_default_context(cafile=certifi.where())
 with urlopen(req,timeout=18,context=tls) as res:
  payload=json.loads(res.read(8000000))
 if not isinstance(payload,dict) or not isinstance(payload.get("data"),list):raise ValueError("Unexpected JSON API schema")
 return payload
def datevalue(v):
 if not v:return None
 if isinstance(v,(int,float)):
  try:return datetime.fromtimestamp(v,timezone.utc).date().isoformat()
  except (ValueError,OverflowError):return None
 s=str(v)
 m=re.search(r"\d{4}-\d{2}-\d{2}",s)
 return m.group(0) if m else None
def included_symbols(obj):
 lookup={}
 for x in obj.get("included",[]):
  a=x.get("attributes") or {}
  symbol=a.get("symbol") or a.get("code") or a.get("field_code")
  name=a.get("libelleFR") or a.get("libelleEN") or a.get("name")
  if isinstance(symbol,dict):symbol=symbol.get("value")
  if symbol:lookup[str(x.get("id"))]=(str(symbol).strip().upper(),str(name or symbol))
 return lookup
def normalized(obj):
 lookup=included_symbols(obj)
 out=[]
 for x in obj.get("data",[]):
  a=x.get("attributes") or {}
  relation=(x.get("relationships") or {}).get("symbol") or {}
  rel=relation.get("data") or {}
  item=lookup.get(str(rel.get("id")))
  if not item:
   ticker=a.get("symbol")
   if isinstance(ticker,dict):ticker=ticker.get("symbol") or ticker.get("value")
   if isinstance(ticker,str) and len(ticker)<=8:item=(ticker.strip().upper(),ticker.strip().upper())
  if not item:continue
  rawdate=a.get("field_seance_date") or a.get("created")
  dt=datevalue(rawdate)
  close=numeric(a.get("closingPrice"))
  if close is None:close=numeric(a.get("coursCourant"))
  volume=numeric(a.get("cumulTitresEchanges"))
  if volume is None:volume=numeric(a.get("cumulVolumeEchange"))
  if not dt or close is None or close<=0 or volume is None or volume<0:continue
  if dt>date.today().isoformat():continue
  out.append({"ticker":item[0],"name":item[1],"row":{"date":dt,"close":close,"volume":volume,"source":"Bourse de Casablanca","source_url":BASE,"quality":"official_json_history"}})
 return out
def main():
 old=json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"companies":[]}
 merged={}
 for x in old.get("companies",[]):
  if x.get("ticker"):
   merged[x["ticker"]]={"ticker":x["ticker"],"name":x.get("name") or x["ticker"],"rows":{q["date"]:q for q in x.get("rows",[]) if q.get("date")}}
 diag={"checked_at":datetime.now(timezone.utc).isoformat(),"source":BASE,"requested_start":os.getenv("EQUITY_BACKFILL_START","2026-06-01"),"pages":0,"records_fetched":0,"rows_parsed":0,"status":"UNVERIFIED"}
 maxpages=min(70,max(1,int(os.getenv("EQUITY_BACKFILL_PAGES","35"))))
 try:
  for i in range(maxpages):
   blob=request(i*LIMIT)
   data=blob["data"]
   if i==0:diag["first_record_schema"]={"attribute_keys":list((data[0].get("attributes") or {}).keys()) if data else [],"relationship_keys":list((data[0].get("relationships") or {}).keys()) if data else [],"included_count":len(blob.get("included",[]))}
   parsed=normalized(blob)
   diag["pages"]+=1;diag["records_fetched"]+=len(data);diag["rows_parsed"]+=len(parsed)
   for x in parsed:
    entry=merged.setdefault(x["ticker"],{"ticker":x["ticker"],"name":x["name"],"rows":{}})
    entry["name"]=x["name"];entry["rows"][x["row"]["date"]]=x["row"]
   if len(data)<LIMIT:break
   time.sleep(.12)
  diag["status"]="SUCCESS" if diag["rows_parsed"] else "NO_ROWS_PARSED"
 except Exception as e:
  diag["status"]="PARTIAL_FAILURE" if diag["rows_parsed"] else "FAILED"
  diag["error"]=type(e).__name__+": "+str(e)[:300]
 result={"schema_version":1,"updated_at":datetime.now(timezone.utc).isoformat(),"companies":[{"ticker":v["ticker"],"name":v["name"],"rows":sorted(v["rows"].values(),key=lambda x:x["date"])} for v in sorted(merged.values(),key=lambda x:x["ticker"])]}
 diag["companies_total"]=len(result["companies"])
 diag["companies_25_sessions"]=sum(len(x["rows"])>=25 for x in result["companies"])
 DIAG.write_text(json.dumps(diag,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 if diag["rows_parsed"]:OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print(json.dumps(diag,ensure_ascii=False))
if __name__=="__main__":main()
