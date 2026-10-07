"""Fail-closed backfill from official Casablanca Stock Exchange daily bulletins."""
import io,json,re,ssl,certifi
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date,timedelta
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
from pypdf import PdfReader

OUT=Path("data/market_history.json")
MEDIA="https://media.casablanca-bourse.com/sites/default/files/es-auto-upload/fr/resume_seance_{ymd}.pdf"
UA="Morocco-Liquidity-Radar/1.3"
TARGET=40
LOOKBACK_DAYS=100
WORKERS=8
TIMEOUT=10
SSL=ssl.create_default_context(cafile=certifi.where())

def get(url):
    r=Request(url,headers={"User-Agent":UA,"Accept":"application/pdf"})
    with urlopen(r,timeout=TIMEOUT,context=SSL) as x:
        b=x.read()
    if not b.startswith(b"%PDF"):
        raise ValueError("response is not a PDF")
    return b

def n(s):
    return float(s.replace("\u202f","").replace("\xa0","").replace(" ","").replace(",", "."))

def candidate_urls():
    d=date.today()
    out=[]
    for i in range(LOOKBACK_DAYS+1):
        x=d-timedelta(days=i)
        if x.weekday()<5:
            out.append((x.isoformat(),MEDIA.format(ymd=x.strftime("%Y%m%d"))))
    return out

def parse_one(expected_date,url):
    raw=get(url)
    txt="\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(raw)).pages)
    flat=re.sub(r"\s+"," ",txt)
    # Bulletin date must match the URL/session date.
    y,m,d=expected_date.split("-")
    patterns=[rf"{d}[/-]{m}[/-]{y}",rf"{y}[/-]{m}[/-]{d}"]
    if not any(re.search(p,flat) for p in patterns):
        return None
    mm=re.search(r"MASI(?!\s*20).*?([\d\s\u00a0\u202f]{4,}[,.]\d{2})",flat,re.I)
    vm=re.search(r"(?:VOLUME\s+(?:GLOBAL|TOTAL)|VOLUME\s+DES\s+ECHANGES).*?([\d\s\u00a0\u202f]{3,})\s*(?:MAD|DH)",flat,re.I)
    if not(mm and vm):
        return None
    row={"date":expected_date,"masi":n(mm.group(1)),"volume_mad":n(vm.group(1)),
         "breadth":None,"source":"Bourse de Casablanca",
         "source_url":url,"quality":"official_bulletin"}
    if not (1000 < row["masi"] < 100000 and 0 <= row["volume_mad"] < 1e12):
        return None
    return row

def main():
    old=json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else []
    by={x["date"]:x for x in old}
    todo=[(d,u) for d,u in candidate_urls() if d not in by]
    ok=0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures={pool.submit(parse_one,d,u):(d,u) for d,u in todo}
        for fut in as_completed(futures):
            d,u=futures[fut]
            try:
                row=fut.result()
                if row:
                    by[row["date"]]=row
                    ok+=1
                    print("validated",row["date"],row["masi"],row["volume_mad"])
            except (HTTPError,URLError,TimeoutError,ValueError) as e:
                print("skip",d,type(e).__name__)
            except Exception as e:
                print("skip",d,type(e).__name__,str(e)[:120])
            if len(by)>=TARGET:
                for pending in futures:
                    pending.cancel()
                break
    if len(by)<5:
        raise SystemExit(f"Only {len(by)} total validated sessions; refusing write.")
    rows=sorted(by.values(),key=lambda x:x["date"])[-120:]
    OUT.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"Backfill complete: {len(rows)} validated sessions ({ok} new).")

if __name__=="__main__":
    main()
