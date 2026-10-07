"""Casablanca Stock Exchange official-data collector (V1).

Primary source: official Bourse de Casablanca pages.
The collector is deliberately fail-closed: if required fields cannot be
validated, it writes nothing to market_history.json.
"""
import json, re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

HOME="https://www.casablanca-bourse.com/"
OUT=Path("data/market_history.json")
UA="Morocco-Liquidity-Radar/1.0 (+GitHub Actions)"

def fetch(url):
    req=Request(url,headers={"User-Agent":UA,"Accept-Language":"fr-FR,fr;q=0.9"})
    with urlopen(req,timeout=30) as r:
        return r.read().decode("utf-8","ignore")

def number(s):
    return float(s.replace("\u202f","").replace(" ","").replace(",", "."))

def parse_home(html):
    # Fallback official snapshot parser. Bulletin/PDF backfill is a separate stage.
    text=re.sub(r"<[^>]+>"," ",html)
    text=re.sub(r"\s+"," ",text)
    masi=re.search(r"MASI\s*[+\-]?\d+[,.]\d+%\s*([\d\s]+[,.]\d+)",text,re.I)
    vol=re.search(r"VOLUME GLOBAL\s*([\d\s]+)\s*MAD",text,re.I)
    if not masi or not vol: return None
    return {"masi":number(masi.group(1)),"volume_mad":number(vol.group(1))}

def validate(row):
    return 1000 < row["masi"] < 100000 and 0 <= row["volume_mad"] < 1e12

def upsert(row):
    rows=json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else []
    rows=[x for x in rows if x.get("date")!=row["date"]]
    rows.append(row); rows.sort(key=lambda x:x["date"])
    OUT.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")

def main():
    html=fetch(HOME)
    p=parse_home(html)
    if not p or not validate(p):
        raise SystemExit("Official market snapshot failed validation; nothing written.")
    # GitHub job runs after market close; date is retrieval date until bulletin confirms session date.
    today=datetime.now(timezone.utc).date().isoformat()
    p.update({"date":today,"source":"Bourse de Casablanca","source_url":HOME,
              "retrieved_at":datetime.now(timezone.utc).isoformat(),
              "quality":"official_snapshot_pending_bulletin_confirmation",
              "breadth":None})
    upsert(p)
    print(json.dumps(p,ensure_ascii=False))

if __name__=="__main__": main()
