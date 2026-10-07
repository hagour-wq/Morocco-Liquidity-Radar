"""Long-history MASI backfill. Fail closed: never invent missing market observations."""
import csv, io, json, re, ssl, certifi
from datetime import date, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

OUT=Path("data/market_history.json")
UA="Mozilla/5.0 Morocco-Liquidity-Radar/2.0"
SSL=ssl.create_default_context(cafile=certifi.where())
TARGET_SESSIONS=500
LOOKBACK_DAYS=1100

# Secondary history endpoints can change. Each parser validates date + plausible MASI.
CANDIDATES=[
 "https://stooq.com/q/d/l/?s=masi&i=d",
]

def get(url):
    req=Request(url,headers={"User-Agent":UA,"Accept":"text/csv,text/plain,*/*"})
    with urlopen(req,timeout=20,context=SSL) as r:return r.read().decode("utf-8","replace")

def plausible(v): return 1000 < v < 100000

def parse_stooq(text):
    rows=[]
    for x in csv.DictReader(io.StringIO(text)):
        try:
            dt=x.get("Date"); close=float(x.get("Close",""))
            if dt and plausible(close):
                rows.append({"date":dt,"masi":close,"volume_mad":None,"breadth":None,
                 "source":"Stooq MASI historical","source_url":CANDIDATES[0],"quality":"secondary_historical_price"})
        except (ValueError,TypeError):pass
    return rows

def main():
    old=json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else []
    by={x["date"]:x for x in old}
    added=0
    for url in CANDIDATES:
        try:
            text=get(url)
            for row in parse_stooq(text):
                if row["date"] not in by:
                    by[row["date"]]=row;added+=1
        except (HTTPError,URLError,TimeoutError,OSError) as e:
            print("secondary source unavailable",type(e).__name__)
    cutoff=(date.today()-timedelta(days=LOOKBACK_DAYS)).isoformat()
    rows=sorted((x for x in by.values() if x["date"]>=cutoff),key=lambda x:x["date"])
    if len(rows)<len(old):
        rows=sorted(by.values(),key=lambda x:x["date"])
    OUT.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"History: {len(rows)} sessions; {added} new. Target={TARGET_SESSIONS}.")
    if added==0:
        print("No new secondary history. Existing validated history preserved.")

if __name__=="__main__":main()
