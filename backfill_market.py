"""Fast, fail-closed backfill from official Casablanca bulletins."""
import io,json,re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request,urlopen
from pypdf import PdfReader

LISTING="https://www.casablanca-bourse.com/market-data/bulletins-de-la-cote"
OUT=Path("data/market_history.json")
UA="Morocco-Liquidity-Radar/1.1"
TARGET=40
MAX_LINKS=60
WORKERS=8
TIMEOUT=8

def get(url,binary=False):
    r=Request(url,headers={"User-Agent":UA,"Accept-Language":"fr-FR,fr;q=0.9"})
    with urlopen(r,timeout=TIMEOUT) as x: b=x.read()
    return b if binary else b.decode("utf-8","ignore")

def n(s): return float(s.replace("\u202f","").replace(" ","").replace(",", "."))

def links(html):
    hs=re.findall(r'href=["\']([^"\']+\.pdf(?:\?[^"\']*)?)',html,re.I)
    out=[]
    for h in hs:
        u=urljoin(LISTING,h)
        if u not in out: out.append(u)
    return out[:MAX_LINKS]

def parse_one(url):
    raw=get(url,True)
    txt="\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(raw)).pages)
    flat=re.sub(r"\s+"," ",txt)
    dm=re.search(r"(\d{2})[/-](\d{2})[/-](20\d{2})",flat)
    mm=re.search(r"MASI(?!\s*20).*?([\d\s]{4,}[,.]\d{2})",flat,re.I)
    vm=re.search(r"(?:VOLUME\s+(?:GLOBAL|TOTAL)|VOLUME\s+DES\s+ECHANGES).*?([\d\s]{3,})\s*(?:MAD|DH)",flat,re.I)
    if not(dm and mm and vm): return None
    row={"date":f"{dm.group(3)}-{dm.group(2)}-{dm.group(1)}","masi":n(mm.group(1)),
         "volume_mad":n(vm.group(1)),"breadth":None,"source":"Bourse de Casablanca",
         "source_url":url,"quality":"official_bulletin"}
    return row if 1000<row["masi"]<100000 and 0<=row["volume_mad"]<1e12 else None

def main():
    discovered=links(get(LISTING))
    if not discovered: raise SystemExit("No official bulletin PDFs discovered.")
    old=json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else []
    by={x["date"]:x for x in old}
    known={x.get("source_url") for x in old}
    todo=[u for u in discovered if u not in known]
    ok=0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures={pool.submit(parse_one,u):u for u in todo}
        for fut in as_completed(futures):
            try:
                row=fut.result()
                if row:
                    by[row["date"]]=row; ok+=1
                    print("validated",row["date"])
            except Exception as e:
                print("skip",type(e).__name__,futures[fut])
            if len(by)>=TARGET:
                for pending in futures: pending.cancel()
                break
    if len(by)<5:
        raise SystemExit(f"Only {len(by)} total validated sessions; refusing write.")
    rows=sorted(by.values(),key=lambda x:x["date"])[-120:]
    OUT.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"Backfill complete: {len(rows)} validated sessions ({ok} new).")

if __name__=="__main__": main()
