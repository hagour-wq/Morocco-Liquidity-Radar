"""Independent global risk collector. Source- and freshness-aware; never substitutes proxies."""
import csv,json,os,xml.etree.ElementTree as ET
from io import StringIO
from datetime import datetime,date,timezone
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import quote
OUT=Path("data/global_inputs.json")
SERIES={"us10y":"DGS10","vix":"VIXCLS","dollar":"DTWEXBGS","sp500":"SP500"}
def get(url):
 req=Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; MoroccoLiquidityRadar/1.0)","Accept":"text/csv,application/json,application/xml,*/*"})
 with urlopen(req,timeout=9) as r: return r.read(9000000).decode("utf-8-sig","replace")
def parse_csv(raw,value_fields):
 rows=[]
 for x in csv.DictReader(StringIO(raw)):
  dt=x.get("DATE") or x.get("observation_date") or x.get("Date")
  if dt and "/" in dt:
   try:dt=datetime.strptime(dt,"%m/%d/%Y").date().isoformat()
   except ValueError:continue
  for field in value_fields:
   try:
    val=float(x[field])
    if dt:rows.append((dt,val))
    break
   except (KeyError,TypeError,ValueError):pass
 return sorted(rows)
def fred(sid):
 urls=[]
 if os.getenv("FRED_API_KEY"):
  urls.append(("FRED_API","https://api.stlouisfed.org/fred/series/observations?series_id="+sid+"&api_key="+os.environ["FRED_API_KEY"]+"&file_type=json&observation_start=2026-07-01"))
 urls.append(("FRED_CSV","https://fred.stlouisfed.org/graph/fredgraph.csv?id="+sid+"&cosd=2026-07-01"))
 for name,url in urls:
  try:
   raw=get(url)
   if name=="FRED_API":
    rows=sorted((x["date"],float(x["value"])) for x in json.loads(raw)["observations"] if x.get("value") not in (None,"."))
   else:rows=parse_csv(raw,[sid])
   if len(rows)>=6:return rows[-30:],name,url
  except Exception:pass
 raise ValueError("FRED unavailable")
def treasury():
 url="https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value="+str(date.today().year)
 root=ET.fromstring(get(url))
 rows=[]
 for element in root.iter():
  if not element.tag.endswith("entry"):continue
  fields={x.tag.split("}")[-1].lower():x.text for x in element.iter()}
  dt=fields.get("new_date")
  val=fields.get("bc_10year")
  try:rows.append((datetime.strptime(dt[:10],"%Y-%m-%d").date().isoformat(),float(val)))
  except (ValueError,TypeError,AttributeError):pass
 if len(rows)<6:raise ValueError("Treasury XML insufficient history")
 return sorted(rows)[-30:],"US_TREASURY",url
def cboe():
 url="https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
 rows=parse_csv(get(url),["CLOSE","Close","close"])
 if len(rows)<6:raise ValueError("Cboe insufficient history")
 return rows[-30:],"CBOE",url
def yahoo(symbol):
 url="https://query1.finance.yahoo.com/v8/finance/chart/"+quote(symbol,safe="")+"?range=1mo&interval=1d"
 obj=json.loads(get(url))["chart"]["result"][0]
 timestamps=obj["timestamp"]
 values=obj["indicators"]["quote"][0]["close"]
 rows=sorted((datetime.fromtimestamp(t,timezone.utc).date().isoformat(),float(v)) for t,v in zip(timestamps,values) if v is not None)
 if len(rows)<6:raise ValueError("Yahoo insufficient history")
 return rows[-30:],"YAHOO_FINANCE",url
def obtain(key,sid):
 failures=[]
 providers=[]
 if key=="vix":providers=[cboe,lambda: yahoo("^VIX")]
 if key=="us10y":providers=[treasury,lambda: yahoo("^TNX")]
 if key=="sp500":providers=[lambda: yahoo("^GSPC")]
 if key=="dollar":providers=[lambda: yahoo("DX-Y.NYB")]
 providers.append(lambda:fred(sid))
 for fun in providers:
  try:
   rows,source,url=fun()
   latest=date.fromisoformat(rows[-1][0])
   age=(date.today()-latest).days
   if age<0 or age>7:raise ValueError("stale "+str(age)+" days")
   return rows,source,url,failures
  except Exception as e:failures.append(fun.__name__+":"+type(e).__name__+":"+str(e)[:75])
 raise ValueError("; ".join(failures))
def clamp(x):return max(-100,min(100,x))
def main():
 previous=json.loads(OUT.read_text()) if OUT.exists() else {}
 d={"checked_at":datetime.now(timezone.utc).isoformat(),"verified":False,"coverage":0,"components":{},"method":"Four equally weighted five-observation risk impulses; experimental diagnostic."}
 parts=[]
 for key,sid in SERIES.items():
  try:
   rows,source,url,failures=obtain(key,sid)
   last,prev=rows[-1],rows[-6]
   change=(last[1]-prev[1])*100 if key=="us10y" else (last[1]/prev[1]-1)*100
   score=clamp(change*{"vix":-4,"us10y":-1.2,"dollar":-8,"sp500":8}[key])
   d["components"][key]={"series":sid,"source":source,"source_url":url,"date":last[0],"value":last[1],"change_5obs":round(change,3),"score":round(score,1),"verified":True,"failed_sources":failures}
   parts.append(score)
  except Exception as e:
   old=previous.get("components",{}).get(key,{})
   try:valid=old.get("verified") and 0<=(date.today()-date.fromisoformat(old["date"])).days<=7
   except (ValueError,TypeError,KeyError):valid=False
   if valid:
    d["components"][key]=dict(old,from_recent_cache=True,refresh_error=str(e)[:240])
    parts.append(float(old["score"]))
   else:d["components"][key]={"series":sid,"verified":False,"error":str(e)[:350]}
 d["coverage"]=round(len(parts)/4,2)
 if parts:
  d["score"]=round(sum(parts)/len(parts))
  d["verified"]=True
 OUT.write_text(json.dumps(d,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
if __name__=="__main__":main()
