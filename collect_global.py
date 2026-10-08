import csv,json
from io import StringIO
from pathlib import Path
from datetime import datetime,timezone
from urllib.request import Request,urlopen
OUT=Path("data/global_inputs.json")
SERIES={"us10y":"DGS10","vix":"VIXCLS","dollar":"DTWEXBGS","sp500":"SP500"}
def get_series(sid):
 u=f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
 req=Request(u,headers={"User-Agent":"Mozilla/5.0"})
 with urlopen(req,timeout=30) as r: txt=r.read().decode()
 rows=[]
 for x in csv.DictReader(StringIO(txt)):
  try: rows.append((x.get("DATE") or x.get("observation_date"),float(x[sid])))
  except: pass
 if len(rows)<6: raise ValueError("insufficient observations")
 return u,rows[-30:]
def clamp(x):return max(-100,min(100,x))
def main():
 d={"checked_at":datetime.now(timezone.utc).isoformat(),"components":{},"verified":False}
 scores=[]
 for k,sid in SERIES.items():
  try:
   u,r=get_series(sid); last=r[-1]; prev=r[-6] if len(r)>=6 else r[0]
   ch=(last[1]/prev[1]-1)*100 if k!="us10y" else (last[1]-prev[1])*100
   d["components"][k]={"series":sid,"source_url":u,"date":last[0],"value":last[1],"change_5obs":round(ch,3),"verified":True}
   if k=="vix": scores.append(clamp(-ch*4))
   elif k=="us10y": scores.append(clamp(-ch*1.2))
   elif k=="dollar": scores.append(clamp(-ch*8))
   elif k=="sp500": scores.append(clamp(ch*8))
  except Exception as e:d["components"][k]={"series":sid,"verified":False,"error":type(e).__name__}
 if len(scores)==len(SERIES):
  d["score"]=round(sum(scores)/len(scores)); d["verified"]=True
  d["method"]="Equal-weight risk impulse: falling VIX/yields/dollar and rising S&P are positive; 5-observation changes, clamped."
 OUT.write_text(json.dumps(d,indent=2)+"\n")
if __name__=="__main__":main()
