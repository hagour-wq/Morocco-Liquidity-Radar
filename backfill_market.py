"""Backfill Casablanca history from official bulletins.

This script discovers official bulletin links from Casablanca Stock Exchange,
extracts PDF text with pypdf, validates date/MASI/volume, and merges only
validated observations. Designed for GitHub Actions manual runs.
"""
import io,json,re
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request,urlopen

from pypdf import PdfReader

LISTING="https://www.casablanca-bourse.com/market-data/bulletins-de-la-cote"
OUT=Path("data/market_history.json")
UA="Morocco-Liquidity-Radar/1.0"

def get(url,binary=False):
    r=Request(url,headers={"User-Agent":UA,"Accept-Language":"fr-FR,fr;q=0.9"})
    with urlopen(r,timeout=40) as x:
        b=x.read()
    return b if binary else b.decode("utf-8","ignore")

def n(s): return float(s.replace("\u202f","").replace(" ","").replace(",", "."))

def pdf_links(html):
    hrefs=re.findall(r'href=["\']([^"\']+\.pdf(?:\?[^"\']*)?)',html,re.I)
    links=[]
    for h in hrefs:
        u=urljoin(LISTING,h)
        if u not in links: links.append(u)
    return links[:90]

def text_pdf(url):
    raw=get(url,True)
    rd=PdfReader(io.BytesIO(raw))
    return "\n".join((p.extract_text() or "") for p in rd.pages)

def parse(txt,url):
    flat=re.sub(r"\s+"," ",txt)
    # Date formats commonly printed in official bulletins.
    dm=re.search(r"(\d{2})[/-](\d{2})[/-](20\d{2})",flat)
    mm=re.search(r"MASI(?!\s*20).*?([\d\s]{4,}[,.]\d{2})",flat,re.I)
    # Prefer MAD global market volume wording.
    vm=re.search(r"(?:VOLUME\s+(?:GLOBAL|TOTAL)|VOLUME\s+DES\s+ECHANGES).*?([\d\s]{3,})\s*(?:MAD|DH)",flat,re.I)
    if not(dm and mm and vm): return None
    date=f"{dm.group(3)}-{dm.group(2)}-{dm.group(1)}"
    row={"date":date,"masi":n(mm.group(1)),"volume_mad":n(vm.group(1)),
         "breadth":None,"source":"Bourse de Casablanca","source_url":url,
         "quality":"official_bulletin"}
    if not(1000<row["masi"]<100000 and 0<=row["volume_mad"]<1e12): return None
    return row

def main():
    html=get(LISTING)
    links=pdf_links(html)
    if not links: raise SystemExit("No official bulletin PDFs discovered.")
    old=json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else []
    by={x["date"]:x for x in old}
    ok=0
    for u in links:
        try:
            row=parse(text_pdf(u),u)
            if row: by[row["date"]]=row; ok+=1
        except Exception as e:
            print("skip",u,type(e).__name__)
    rows=sorted(by.values(),key=lambda x:x["date"])[-120:]
    if ok<5: raise SystemExit(f"Only {ok} bulletins validated; refusing backfill.")
    OUT.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"Validated {ok} bulletins; history now {len(rows)} sessions.")

if __name__=="__main__": main()
