import csv,json,os
from io import StringIO
from pathlib import Path
from datetime import datetime,timezone,date
from urllib.request import Request,urlopen
OUT=Path("data/global_inputs.json")
SERIES={"us10y":"DGS10","vix":"VIXCLS","dollar":"DTWEXBGS","sp500":"SP500"}
def download(url):
 with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0","Accept":"text/csv,application/json"}),timeout=10) as r:return r.read().decode()
def observations(sid):
 sources=[
  ("FRED_CSV",f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd=2026-07-01"),
  ("FRED_MIRROR",f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"),
 ]
 if os.getenv("FRED_API_KEY"):
  sources.insert(0,("FRED_API",f"https://api.stlouisfed.org/fred/series/observations?series_id={sid}&api_key={os.environ['FRED_API_KEY']}&file_type=json&observation_start=2026-07-01"))
 errors=[]
 for name,url in sources:
  try:
   raw=download(url)
   if name=="FRED_API":
    items=[(x["date"],float(x["value"])) for x in json.loads(raw)["observations"] if x["value"]!="."]
   else:
    items=[]
    for x in csv.DictReader(StringIO(raw)):
     try:items.append((x.get("DATE") or x.get("observation_date"),float(x[sid])))
     except (ValueError,TypeError,KeyError):pass
   items=[(d,v) for d,v in items if d]
   if len(items)>=6:return name,url,items[-30:]
   errors.append(name+":insufficient_history")
  except Exception as e:errors.append(name+":"+type(e).__name__)
 raise RuntimeError(";".join(errors))
def clamp(x):return max(-100,min(100,x))
def fresh(components):
 if len(components)!=4:return False
 try:return all(x.get("verified") and 0<=(date.today()-date.fromisoformat(x["date"])).days<=7 for x in components.values())
 except (KeyError,ValueError,TypeError):return False
def main():
 previous=json.loads(OUT.read_text()) if OUT.exists() else {}
 d={"checked_at":datetime.now(timezone.utc).isoformat(),"components":{},"verified":False}
 scores=[]
 for key,sid in SERIES.items():
  try:
   source,url,rows=observations(sid);last=rows[-1];prev=rows[-6]
   change=(last[1]-prev[1])*100 if key=="us10y" else (last[1]/prev[1]-1)*100
   d["components"][key]={"series":sid,"source":source,"source_url":url,"date":last[0],"value":last[1],"change_5obs":round(change,3),"verified":True}
   factor={"vix":-4,"us10y":-1.2,"dollar":-8,"sp500":8}[key]
   scores.append(clamp(change*factor))
  except Exception as e:d["components"][key]={"series":sid,"verified":False,"error":str(e)[:250]}
 if len(scores)==4 and fresh(d["components"]):
  d["score"]=round(sum(scores)/4);d["verified"]=True
  d["method"]="Equal-weight five-observation risk impulse, exploratory; not a predictive model."
 if not d["verified"] and previous.get("verified") and fresh(previous.get("components",{})):
  previous["last_attempt"]=d;d=previous
 OUT.write_text(json.dumps(d,indent=2)+"\n")
if __name__=="__main__":main()
