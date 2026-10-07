import json, re
from pathlib import Path
from datetime import datetime, timezone
from urllib.request import Request, urlopen

OUT=Path("data/global_inputs.json")
SOURCES={
 "dxy":"https://www.investing.com/indices/usdollar-historical-data",
 "us10y":"https://www.investing.com/rates-bonds/u.s.-10-year-bond-yield-historical-data",
 "vix":"https://www.investing.com/indices/volatility-s-p-500-historical-data",
 "sp500":"https://www.investing.com/indices/us-spx-500-historical-data"
}
def fetch(url):
 req=Request(url,headers={"User-Agent":"Mozilla/5.0"})
 with urlopen(req,timeout=30) as r:return r.read().decode("utf-8","ignore")
def main():
 d={"checked_at":datetime.now(timezone.utc).isoformat(),"components":{},"verified":False,
    "rule":"Global score activates only when numeric parsers are validated; no silent estimates."}
 for k,u in SOURCES.items():
  try:
   h=fetch(u)
   d["components"][k]={"source_url":u,"http_ok":True,"bytes":len(h),"status":"DISCOVERED_NOT_SCORED"}
  except Exception as e:d["components"][k]={"source_url":u,"http_ok":False,"error":type(e).__name__}
 OUT.write_text(json.dumps(d,indent=2)+"\n")
if __name__=="__main__":main()
