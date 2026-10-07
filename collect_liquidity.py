"""Official liquidity collector skeleton.
Never fabricates values: only writes a component after a source-specific parser
has produced a numeric value, a comparison basis and a reference date.
"""
import json
import re
from pathlib import Path
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

P=Path("data/liquidity_inputs.json")

def load():
    return json.loads(P.read_text(encoding="utf-8"))

def save(d):
    d["collector_checked_at"]=datetime.now(timezone.utc).isoformat()
    P.write_text(json.dumps(d,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

def validate_component(x):
    if not x.get("verified"): return True
    return isinstance(x.get("score"),(int,float)) and bool(x.get("reference_date")) and bool(x.get("source"))

def fetch_text(url):
    req=Request(url,headers={"User-Agent":"Mozilla/5.0 EquityBourse/1.0"})
    with urlopen(req,timeout=25) as r:
        return r.read().decode("utf-8","ignore")

def discover_links(page_url, patterns):
    """Return candidate official files/endpoints without trusting their contents."""
    try: html=fetch_text(page_url)
    except Exception as e:
        print("Discovery failed",page_url,type(e).__name__); return []
    links=re.findall(r'''href=["']([^"']+)["']''',html,re.I)
    out=[]
    for href in links:
        low=href.lower()
        if any(p in low for p in patterns):
            if href.startswith("/"):
                from urllib.parse import urljoin
                href=urljoin(page_url,href)
            if href.startswith("http"): out.append(href)
    return list(dict.fromkeys(out))

def main():
    d=load()
    # Discovery layer: official pages only. Parsing/scoring remains gated.
    candidates={
      "ammc":discover_links("https://www.ammc.ma/fr/donnees-statistiques",["opcvm",".xlsx",".xls",".csv"]),
      "bam":discover_links("https://www.bkam.ma/Marches/Principaux-indicateurs/Marche-monetaire/Marche-monetaire",[".xlsx",".xls",".csv","marche","monetaire"])
    }
    d["discovery"]={k:{"count":len(v),"candidates":v[:20]} for k,v in candidates.items()}
    # Safety gate: until a parser validates comparable official observations,
    # existing verified values are preserved and unavailable components remain null.
    for name,x in d.get("components",{}).items():
        if not validate_component(x):
            raise ValueError(f"Invalid verified liquidity component: {name}")
    save(d)
    active=[k for k,v in d["components"].items() if v.get("verified")]
    print("Verified liquidity components:", ", ".join(active) or "none")

if __name__=="__main__": main()
